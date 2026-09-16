# D259 mechanically derived cache-effect matrix

| phase | condition | oem_effect | linux_first_live_policy | required_for_final_0x32 | required_for_device_progress | host_cache_write_count_in_minimal_candidate | derivation |
| --- | --- | --- | --- | --- | --- | --- | --- |
| before_final_0x32 | parsed_dirty_flag_nonzero | HOST_CACHE_SAVE_GOODIX_DAT_CONDITIONAL | DISABLED | False | False | 0 | 0x1800697d8 test -> 0x1800697e1 host cache call; caller arm later |
