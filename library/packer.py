#!/usr/bin/python -tt
# -*- coding: utf-8 -*-

# The MIT License (MIT)
#
# Copyright (c) 2014 Austin Hyde
# Copyright (c) 2016 Matt Schreiber <mschreiber@gmail.com>
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

DOCUMENTATION = '''
---
module: packer
short_description: Manage AUR packages with I(packer)
description:
    - Manage AUR packages with the I(packer) AUR helper.
version_added: "2.1"
author:
    - "Austin Hyde"
    - "'Matt Schreiber (@BaxterStockman)' <mschreiber@gmail.com>"
requirements: []
options:
    name:
        description:
            - Name of the AUR package to install, upgrade, or remove.
        required: false
        default: null

    state:
        description:
            - Desired state of the package.
        required: false
        default: "present"
        choices: ["present", "absent", "latest"]

    recurse:
        description:
            - When removing a package, also remove its dependencies, provided
              that they are not required by other packages and were not
              explicitly installed by a user.
        required: false
        default: no
        choices: ["yes", "no"]

    force:
        description:
            - When removing package - force remove package, without any
              checks. When update_cache - force redownload repo
              databases.
        required: false
        default: no
        choices: ["yes", "no"]

    upgrade:
        description:
            - Whether or not to upgrade all AUR packages
        required: false
        default: no
        choices: ["yes", "no"]
        version_added: "2.0"

notes:
  - Because the C(makepkg) executable responsible for building and installing
    AUR packages disallows running as root, this module attempts to infer
    whether the user escalated privileges and, if so, who the "real" user is.
    If you use C(become) or C(ansible_user=root), the managed system B(must)
    have C(sudo) present in order to downgrade privileges.  However, since
    actually B(installing) packages requires root privileges, you must either
    use C(become) or C(ansible_user=root), or log in with a user with
    passwordless C(sudo) rights.
  - Removal operations are passed through to and accept the same options as the
    I(pacman) module, sinceAUR packages are removed in exactly the same manner
    as prebuilt binary packages.
'''

EXAMPLES = '''
# Install AUR package cower
- packer: name=foo state=present

# Upgrade package cower
- packer: name=cower state=latest

# Remove packages cower, meat
- packer: name=cower,meat state=absent

# Recursively remove package aura
- packer: name=aura state=absent recurse=yes

# Run the equivalent of "packer -Syu" as a separate step
- packer: upgrade=yes

# Run the equivalent of "pacman -Syu" as a separate step
- pacman: update_cache=yes upgrade=yes

# Run the equivalent of "pacman -Rdd", force remove package aura
- pacman: name=aura state=absent force=yes
'''

import os
import pwd
import re

class Packer(object):
    def __init__(self, module):
        self.module = module

        self.packer_path = self.module.get_bin_path('packer')
        if self.packer_path is None:
            self.module.fail_json(msg='unable to find packer executable')

        self.expac_path = self.module.get_bin_path('expac')
        if self.expac_path is None:
            self.module.fail_json(msg='unable to find expac executable')

    def run(self):
        pkgs = self.module.params.get('name', [])
        if pkgs is None:
            pkgs = []

        normalized_state = self.normalized_state()

        failed = False
        changed = False

        would_update, already_present, not_found = self.check_packages(pkgs)

        would_update_msg = 'all packages already %s' % normalized_state
        already_present_msg = None
        not_found_msg = None

        if len(would_update) >= 1:
            would_update_msg = 'would update %s' % ', '.join(would_update)
            changed = True
        if len(already_present) >= 1:
            already_present_msg = '%s already %s' % (', '.join(already_present), normalized_state)
        if len(not_found) >= 1:
            not_found_msg = 'could not find %s' % ', '.join(not_found)
            failed = True

        if self.module.check_mode:
            msg_e = [msg for msg in [would_update_msg, already_present_msg, not_found_msg] if msg is not None]
            self.module.exit_json(changed=changed, msg='; '.join(msg_e))
        elif failed:
            self.module.fail_json(msg=not_found_msg)
        elif not changed and not self.should_upgrade():
            self.module.exit_json(changed=changed, msg=would_update_msg)
        else:
            self.install_packages(would_update)

    def normalized_state(self):
        state = self.module.params.get('state', None)

        if state in ['present', 'installed']:
            return 'present'
        elif state in ['latest']:
            return 'latest'
        else:
            return None

    def should_update(self):
        self.normalized_state == 'latest'

    def should_upgrade(self):
        return self.module.params.get('upgrade', False)

    def package_installed_version(self, name):
        rc, stdout, stderr = self.module.run_command("%s -Q '%%v' %s" % (self.expac_path, name))

        if rc != 0:
            return None

        return stdout.splitlines()[0].strip()

    def package_info(self, name):
        rc, stdout, stderr = self.module.run_command('%s -Si --auronly %s' % (self.packer_path, name), check_rc=False)

        if rc != 0:
            return None

        # Only lines that don't start with spaces represent metadata keys.
        # Other lines are continuations of values; e.g., optional dependencies.
        line_acc = []
        for line in stdout.splitlines():
            if re.match('^\s', line):
                try:
                    line_acc[-1] += ' ' + line.strip()
                except IndexError:
                    line_acc.append(line.strip())
            else:
                line_acc.append(line.strip())

        split_on_colons = re.compile(r'^(.*)\s+:\s*(.*)')
        kv_pairs = [re.findall(split_on_colons, line)[0] for line in line_acc if line != '']
        return dict([(re.sub(r'\s+', '_', k.strip()).lower(), v.strip()) for k, v in kv_pairs])

    def login_name(self):
        login_name = None

        try:
            login_name = os.getlogin()
        except OSError:
            logname_path = self.module.get_bin_path('logname')

            if logname_path:
                rc, stdout, stderr = self.module.run_command(logname_path, check_rc=False)

                if rc == 0 and stdout != '':
                    login_name = stdout.splitlines()[0].strip()

            if login_name is None:
                login_name = os.environ.get('LOGNAME')

            if login_name is None or login_name == 'root':
                login_name = os.environ.get('SUDO_USER', login_name)

        return login_name

    def check_packages(self, pkgs):
        would_change = []
        already_present = []
        not_found = []

        should_update = self.should_update()

        for name in pkgs:
            package_info = self.package_info(name)

            if package_info is None:
                not_found.append(name)
                continue

            package_installed_version = self.package_installed_version(name)

            if should_update:
                if package_installed_version is None or package_installed_version != package_info['version']:
                    would_change.append(name)
                else:
                    already_present.append(name)
            else:
                if package_installed_version is None:
                    would_change.append(name)
                else:
                    already_present.append(name)

        return would_change, already_present, not_found

    def install_packages(self, pkgs):
        if pkgs is None:
            pkgs = []

        login_name = self.login_name()

        switched_user = pwd.getpwuid(os.getuid())[0] != login_name

        if switched_user:
            sudo_path = self.module.get_bin_path('sudo')

            if sudo_path is None:
                self.module.fail_json(msg='unable to locate sudo executable')

            base_cmd = '%s -u %s %s' % (sudo_path, login_name, self.packer_path)
        else:
            base_cmd = '%s' % self.packer_path

        base_cmd += ' --auronly --noconfirm --noedit'

        root = self.module.params.get('root')
        if root:
          base_cmd += ' --root %s' % root

        if self.should_upgrade():
            cmd = '%s -Syu' % base_cmd
            rc, stdout, stderr = self.module.run_command(cmd, check_rc=False)

            if rc != 0:
                self.module.fail_json(msg='failed to upgrade packages: %s' % stderr)

            if len(pkgs) < 1:
                self.module.exit_json(changed=True, msg='upgraded AUR packages')

        changed = False
        total_installed = 0

        for name in pkgs:
            cmd = '%s -S %s' % (base_cmd, name)
            rc, stdout, stderr = self.module.run_command(cmd, check_rc=False)

            if rc != 0:
                msg = 'failed to install package %s: %s' % (name, stderr)

                if not switched_user:
                    msg += ' (do you have passwordless sudo as user %s?)' % login_name

                self.module.fail_json(msg=msg)

            total_installed += 1

        changed |= total_installed >= 1

        self.module.exit_json(changed=changed, msg='installed %s package(s)' % total_installed)

def main():
    module = AnsibleModule(
        argument_spec = dict(
            name         = dict(type='list', aliases=['pkg', 'package']),
            state        = dict(default='present', choices=['present', 'installed', 'latest']),
            root         = dict(required=False, type='str'),
            upgrade      = dict(type='bool'),
            # Here just for compatibility with the 'pacman' module
            force        = dict(default=False, type='bool'),
        ),
        supports_check_mode = True,
        required_one_of = [['name', 'upgrade']],
    )

    packer = Packer(module)

    return packer.run()

from ansible.module_utils.basic import *

if __name__ == '__main__':
    main()
