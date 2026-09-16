#!/bin/sh

po_dir=$(dirname $0)

for i in $po_dir/*.po ; do
    if ! grep -q `basename $i | sed 's,.po,,'` $po_dir/LINGUAS; then
        echo '**********************************';
        echo '***' `basename $i | sed 's,.po,,'` missing from po/LINGUAS '***' ;
        echo '**********************************';
        exit 1;
    fi;
done;

exit 0
