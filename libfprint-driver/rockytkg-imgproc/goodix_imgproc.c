/* goodix_imgproc.c - 图像预处理参数化管线（16bit 帧 -> 8bit 灰度）
 *
 * 各环节可经 struct gx_imgproc_params 调整。
 *
 * 管线（每帧调用，无 static 缓冲，可重入）：
 *   1) baseline  可选减无手指基线：v = offset + raw - base，clamp [0,4095]。
 *      2048 余量提供对称空间，避免半波整流/饱和；基线无效时直接用原帧。
 *   2) flatfield 可选去低频背景：可分离盒式均值（半径远大于脊距，只移除
 *      接触压力造成的缓慢亮度梯度），v = clamp(v - lowf + mean_all, 0, 4095)，
 *      同步累计直方图（mean_all 为平场前的均值，与原实现运算顺序一致）。
 *   3) stretch   pct_lo/pct_hi 百分位截断映射到 0..255（hi<=lo 回退全量程）。
 *   4) enhance   可选反锐化局部对比增强（SIGFM/SIFT 定向）：对 8bit 输出
 *      out = clamp(in + boost*(in - gauss(in,σ)))。SIGFM 的 sigfm_extract()
 *      用 SIFT 默认 contrastThreshold=0.04，弱脊/轻触下关键点常低于 fork 的
 *      25 个下限——本环节提升脊谷局部对比度，可提高关键点通过率。
 *      反锐化同时放大噪点，默认关闭（GX_IMGPROC_ENHANCE_NONE），
 *      靠 SIGFM 的几何一致性投票过滤假关键点。
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "goodix_imgproc.h"

#include <limits.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>

/*
 * ADAPTED_FROM_ROCKY:
 *   Rockytkg/src/goodix_imgproc.c
 *   commit 227eba219fa9e3fbac5bd59aca79f624f67cd11b
 *
 * Adaptation boundary: detach the pure image pipeline from goodix_dev and
 * remove getenv/debug-dump paths. No USB, TLS, persistent storage or device
 * lifecycle code is imported. Algorithm stages and fixed parameters remain
 * those of the preserved source.
 */

#define IMGPROC_PX_MAX   4095            /* 12bit 像素有效上界 */
#define IMGPROC_CLAMP16(v) ((v) < 0 ? 0 : (v) > IMGPROC_PX_MAX ? IMGPROC_PX_MAX : (v))

static inline uint16_t imgproc_px16(const uint8_t *img, uint32_t idx)
{
    return (uint16_t)(img[2 * idx] | (img[2 * idx + 1] << 8));
}

/* ---- 可分离盒式均值（水平+垂直一维前缀和，半径 r，边界复制）----
 * 用于低频亮度场估计。原实现用 static 缓冲且按 GF_IMG_MAX/2 硬编码尺寸，
 * 这里改为每次调用按实际 w*h 动态分配，保证可重入。返回 0 成功、-1 分配失败。 */
static int boxmean(const uint16_t *in, uint16_t *out,
                   uint32_t w, uint32_t h, int r)
{
    uint32_t npix = w * h;
    uint32_t pslen = (w > h ? w : h) + 1;
    uint32_t radius = (uint32_t)r;
    uint32_t *tmp = malloc((size_t)npix * sizeof(uint32_t));
    uint32_t *ps = malloc((size_t)pslen * sizeof(uint32_t));
    uint32_t x, y;

    if (!tmp || !ps) {
        free(tmp);
        free(ps);
        return -1;
    }
    /* 水平 pass */
    for (y = 0; y < h; y++) {
        const uint16_t *row = &in[y * w];
        ps[0] = 0;
        for (x = 0; x < w; x++)
            ps[x + 1] = ps[x] + row[x];
        for (x = 0; x < w; x++) {
            uint32_t x0 = x > radius ? x - radius : 0;
            uint32_t x1 = x + radius < w ? x + radius : w - 1;
            tmp[y * w + x] = (ps[x1 + 1] - ps[x0]) / (x1 - x0 + 1);
        }
    }
    /* 垂直 pass */
    for (x = 0; x < w; x++) {
        ps[0] = 0;
        for (y = 0; y < h; y++)
            ps[y + 1] = ps[y] + tmp[y * w + x];
        for (y = 0; y < h; y++) {
            uint32_t y0 = y > radius ? y - radius : 0;
            uint32_t y1 = y + radius < h ? y + radius : h - 1;
            out[y * w + x] = (uint16_t)((ps[y1 + 1] - ps[y0]) / (y1 - y0 + 1));
        }
    }
    free(tmp);
    free(ps);
    return 0;
}

/* ---- stage 1: 有符号基线相减 ----
 * use_baseline 且 d->img_base_valid 时 v = offset + raw - base（clamp）；
 * 否则直接用原帧（等价原实现的无基线分支）。 */
static void stage_baseline(const struct gx_imgproc_frame *frame,
                           const uint8_t *img16,
                           uint16_t *buf, int use_baseline, uint16_t offset)
{
    uint32_t npix = frame->width * frame->height;
    for (uint32_t i = 0; i < npix; i++) {
        uint16_t r = imgproc_px16(img16, i);
        if (use_baseline && frame->baseline_valid) {
            uint16_t b = imgproc_px16(frame->baseline16le, i);
            int v = (int)offset + (int)r - (int)b;
            buf[i] = (uint16_t)IMGPROC_CLAMP16(v);
        } else {
            buf[i] = r;
        }
    }
}

/* ---- stage 2: 低频平场校正 + 直方图累计 ----
 * mean_all 来自平场前的 buf 均值（与原实现顺序一致）；clamp 后 buf[i]
 * 必在 [0,4095]，直方图索引无需掩码。返回 0 成功、-1 分配失败（调用方
 * 回退为"无平场"直方图路径，输出仍合法）。 */
static int stage_flatfield(uint16_t *buf, uint32_t w, uint32_t h, int r,
                           uint32_t *hist)
{
    uint32_t npix = w * h;
    uint16_t *lowf = malloc((size_t)npix * sizeof(uint16_t));
    uint64_t sum = 0;
    uint32_t mean_all;

    if (!lowf)
        return -1;
    if (boxmean(buf, lowf, w, h, r) < 0) {
        free(lowf);
        return -1;
    }
    for (uint32_t i = 0; i < npix; i++)
        sum += buf[i];
    mean_all = (uint32_t)(sum / npix);
    for (uint32_t i = 0; i < npix; i++) {
        int v = (int)buf[i] - (int)lowf[i] + (int)mean_all;
        buf[i] = (uint16_t)IMGPROC_CLAMP16(v);
        hist[buf[i]]++;
    }
    free(lowf);
    return 0;
}

/* ---- stage 3: 百分位截断 -> 0..255 ----
 * pct_lo/pct_hi 定义保留区间 [pct_lo%, pct_hi%]：底部截断 pct_lo%、
 * 顶部截断 (100-pct_hi)%。原实现向下扫描用 npix/100（顶部累计 1%），
 * 即默认 pct_hi=99 等价顶部截断 1%。 */
static void stage_stretch(const uint16_t *buf, uint8_t *out8,
                          uint32_t npix, const uint32_t *hist,
                          uint8_t pct_lo, uint8_t pct_hi)
{
    uint32_t lo = 0, hi = IMGPROC_PX_MAX;
    uint32_t n_lo = (uint32_t)((uint64_t)npix * pct_lo / 100);
    uint32_t n_hi = (uint32_t)((uint64_t)npix * (100 - pct_hi) / 100);
    uint32_t acc = 0;

    for (int v = 0; v <= IMGPROC_PX_MAX; v++) {
        acc += hist[v];
        if (acc > n_lo) {
            lo = (uint32_t)v;
            break;
        }
    }
    acc = 0;
    for (int v = IMGPROC_PX_MAX; v >= 0; v--) {
        acc += hist[v];
        if (acc > n_hi) {
            hi = (uint32_t)v;
            break;
        }
    }
    if (hi <= lo) {
        lo = 0;
        hi = IMGPROC_PX_MAX;
    }

    for (uint32_t i = 0; i < npix; i++) {
        uint32_t v = buf[i];
        if (v <= lo)
            out8[i] = 0;
        else if (v >= hi)
            out8[i] = 255;
        else
            out8[i] = (uint8_t)((v - lo) * 255 / (hi - lo));
    }
}

/* ---- stage 4: 可选反锐化（SIGFM 定向，8bit 域）----
 * out = clamp(in + boost*(in - gauss(in,σ)))，可分离高斯、边界复制。 */
static void gaussian_blur_u8(const uint8_t *in, uint8_t *out,
                             uint32_t w, uint32_t h, float sigma)
{
    int r = (int)ceilf(3.0f * sigma);
    int klen;
    float *k;
    uint8_t *tmp;
    float ksum = 0.0f;
    uint32_t x, y;

    if (r < 1)
        r = 1;
    klen = 2 * r + 1;
    k = malloc((size_t)klen * sizeof(float));
    tmp = malloc((size_t)w * h);
    if (!k || !tmp) {
        free(k);
        free(tmp);
        memcpy(out, in, (size_t)w * h);
        return;
    }
    for (int i = -r; i <= r; i++) {
        float t = (float)i;
        k[i + r] = expf(-(t * t) / (2.0f * sigma * sigma));
        ksum += k[i + r];
    }
    for (int i = 0; i < klen; i++)
        k[i] /= ksum;

    /* 水平 pass（边界复制） */
    for (y = 0; y < h; y++) {
        const uint8_t *row = &in[y * w];
        for (x = 0; x < w; x++) {
            float acc = 0.0f;
            for (int j = -r; j <= r; j++) {
                int sx = (int)x + j;
                if (sx < 0)
                    sx = 0;
                else if ((uint32_t)sx >= w)
                    sx = (int)w - 1;
                acc += k[j + r] * row[sx];
            }
            tmp[y * w + x] = (uint8_t)(acc + 0.5f);
        }
    }
    /* 垂直 pass */
    for (x = 0; x < w; x++) {
        for (y = 0; y < h; y++) {
            float acc = 0.0f;
            for (int j = -r; j <= r; j++) {
                int sy = (int)y + j;
                if (sy < 0)
                    sy = 0;
                else if ((uint32_t)sy >= h)
                    sy = (int)h - 1;
                acc += k[j + r] * tmp[(uint32_t)sy * w + x];
            }
            out[y * w + x] = (uint8_t)(acc + 0.5f);
        }
    }
    free(k);
    free(tmp);
}

static void stage_enhance(const uint8_t *in, uint8_t *out,
                          uint32_t w, uint32_t h, float boost, float sigma)
{
    uint8_t *blur = malloc((size_t)w * h);
    if (!blur) {
        memcpy(out, in, (size_t)w * h);
        return;
    }
    gaussian_blur_u8(in, blur, w, h, sigma);
    for (uint32_t i = 0; i < w * h; i++) {
        int d = (int)in[i] - (int)blur[i];
        int v = (int)in[i] + (int)lroundf(boost * (float)d);
        out[i] = (uint8_t)(v < 0 ? 0 : v > 255 ? 255 : v);
    }
    free(blur);
}

/* ---- 公共入口 ---- */
int gx_imgproc_to8bit(const struct gx_imgproc_frame *frame,
                      const struct gx_imgproc_params *p,
                      const uint8_t *img16, uint8_t *out8)
{
    uint32_t w, h, npix;
    uint16_t *buf;
    uint32_t hist[IMGPROC_PX_MAX + 1];

    if (!frame || !img16 || !out8 || !p)
        return -1;
    w = frame->width;
    h = frame->height;
    if (w == 0 || h == 0 || w > UINT32_MAX / h)
        return -1;
    if (p->baseline && frame->baseline_valid && !frame->baseline16le)
        return -1;
    if (p->flatfield && p->flatfield_r < 0)
        return -1;
    if (p->pct_lo > p->pct_hi || p->pct_hi > 100)
        return -1;
    npix = w * h;
    memset(hist, 0, sizeof(hist));

    buf = malloc((size_t)npix * sizeof(uint16_t));
    if (!buf)
        return -1;

    stage_baseline(frame, img16, buf, p->baseline, p->baseline_offset);

    if (p->flatfield) {
        if (stage_flatfield(buf, w, h, p->flatfield_r, hist) != 0) {
            /* 平场分配失败：回退为无平场直方图（输出仍合法） */
            for (uint32_t i = 0; i < npix; i++)
                hist[buf[i]]++;
        }
    } else {
        /* 无平场：直接用 buf 建直方图（clamp 后值在 [0,4095]） */
        for (uint32_t i = 0; i < npix; i++)
            hist[buf[i]]++;
    }

    stage_stretch(buf, out8, npix, hist, p->pct_lo, p->pct_hi);
    free(buf);

    if (p->enhance == GX_IMGPROC_ENHANCE_SIGFM && p->enhance_sigma > 0.0f) {
        stage_enhance(out8, out8, w, h, p->enhance_boost, p->enhance_sigma);
    }

    return 0;
}
