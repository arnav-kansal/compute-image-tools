#!/usr/bin/env python3
# Copyright 2022 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Convert Ubuntu ISO to GCE Image and prep for installation.

Parameters (retrieved from instance metadata):
ubuntu_release: The Ubuntu release to build.
"""

import difflib
import logging
import os
import re

import utils

def main():
  # Get Parameters
  release = utils.GetMetadataAttribute(
      'ubuntu_release', raise_on_not_found=True)

  logging.info('Ubuntu Release: %s' % release)
  logging.info('Build working directory: %s' % os.getcwd())

  iso_file = '/files/installer.iso'
  autoinstall_cfg = '/files/autoinstall.yaml'
  metadata_file = '/files/meta-data'

  # Write the installer disk. Write GPT label, create partition,
  # copy installer boot files over.
  logging.info('Writing installer disk.')

  installer_disk = ('/dev/' + os.path.basename(
      os.readlink('/dev/disk/by-id/google-disk-installer')))

  utils.Execute(['parted', installer_disk, 'mklabel', 'gpt'])
  utils.Execute(['sync'])
  utils.Execute(['parted', installer_disk, 'mkpart', 'primary', 'fat32', '1MB',
                 '4096MB'])
  utils.Execute(['sync'])
  utils.Execute(['parted', installer_disk, 'mkpart', 'primary', 'ext4',
                 '4096MB', '100%'])
  utils.Execute(['sync'])
  utils.Execute(['parted', installer_disk, 'set', '1', 'boot', 'on'])
  utils.Execute(['sync'])
  utils.Execute(['parted', installer_disk, 'set', '1', 'esp', 'on'])
  utils.Execute(['sync'])

  installer_disk1 = ('/dev/' + os.path.basename(
      os.readlink('/dev/disk/by-id/google-disk-installer-part1')))
  installer_disk2 = ('/dev/' + os.path.basename(
      os.readlink('/dev/disk/by-id/google-disk-installer-part2')))

  utils.Execute(['mkfs.vfat', '-F', '32', installer_disk1])
  utils.Execute(['sync'])
  utils.Execute(['fatlabel', installer_disk1, 'cidata'])
  utils.Execute(['sync'])
  utils.Execute(['mkfs.ext4', '-L', 'INSTALLER', installer_disk2])
  utils.Execute(['sync'])

  utils.Execute(['mkdir', '-vp', 'iso', 'installer', 'boot'])
  utils.Execute(['mount', '-o', 'ro,loop', '-t', 'iso9660', iso_file, 'iso'])
  utils.Execute(['mount', '-t', 'vfat', installer_disk1, 'boot'])
  utils.Execute(['mount', '-t', 'ext4', installer_disk2, 'installer'])
  
  # Copy only necessary files, not the whole ISO
  utils.Execute(['cp', '-r', 'iso/boot', 'boot/'])
  utils.Execute(['cp', '-r', 'iso/casper', 'boot/'])
  utils.Execute(['cp', '-r', 'iso/EFI', 'boot/'])
  utils.Execute(['cp', autoinstall_cfg, 'boot/user-data'])
  utils.Execute(['cp', metadata_file, 'boot/meta-data'])
  utils.Execute(['cp', iso_file, 'installer/installer.iso'])


  # Modify boot config.
  with open('boot/boot/grub/grub.cfg', 'r+') as f:
    oldcfg = f.read()
    # Add autoinstall parameters to the linux kernel line.
    args = ' '.join([
      'autoinstall', 'ds=nocloud', 'iso-scan/filename=/installer.iso',
      'console=ttyS0,115200'
    ])
    cfg = re.sub(r'(linux\s+/casper/vmlinuz.*?)\s+---', r'\1 %s ---' % args, oldcfg, flags=re.DOTALL)
    cfg = re.sub(r'timeout=30', 'timeout=1', cfg)
    cfg = re.sub(r'set default=.*', 'set default="0"', cfg)


    # Print out a the modifications.
    diff = difflib.Differ().compare(
        oldcfg.splitlines(1),
        cfg.splitlines(1))
    logging.info('Modified grub.cfg:\n%s' % '\n'.join(diff))

    f.seek(0)
    f.write(cfg)
    f.truncate()

  utils.Execute(['umount', 'installer'])
  utils.Execute(['umount', 'iso'])
  utils.Execute(['umount', 'boot'])


if __name__ == '__main__':
  try:
    main()
    logging.success('Ubuntu Installer build successful!')
  except Exception as e:
    logging.error('Ubuntu Installer build failed: %s' % str(e))
