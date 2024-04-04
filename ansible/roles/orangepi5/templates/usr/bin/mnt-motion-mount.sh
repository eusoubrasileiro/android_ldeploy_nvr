#!/bin/bash

# NFS mount options
NFS_SERVER="192.168.0.45"
NFS_SHARE_PATH="/mnt/motion"
NFS_MOUNT_POINT="/mnt/motion"

sudo mount -t nfs -o rw,nfsvers=3 "$NFS_SERVER":"$NFS_SHARE_PATH" "$NFS_MOUNT_POINT"    

# add this to `sudo visudo` passwordless sudo for this specific file!!!
# andre ALL=(ALL) NOPASSWD: /usr/bin/mnt-motion-mount.sh
# python will then be able to call this without sudo
