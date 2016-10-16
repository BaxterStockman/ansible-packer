# ansible-packer

An Ansible module for installing [AUR](https://aur.archlinux.org/) packages via
the [packer][packer] AUR helper.

This module assumes your managed nodes already have [packer][packer] and its
dependencies installed.

## Dependencies (Managed Node)

* [Arch Linux](https://www.archlinux.org/) (Naturally)
* [jshon](https://www.archlinux.org/packages/community/x86_64/jshon/)
* [packer][packer]

## Installation

1. Clone this repo
2. Copy or link the `library/packer.py` file into your global Ansible library
   (usually `/usr/share/ansible`) or into the `./library` folder alongside your
   top-level playbook

Alternatively, add this to your `requirements.yml`:

```yaml
- src: "https://github.com/BaxterStockman/ansible-packer.git"
  name: packer
```

Then, include the role in your playbook to access the `packer` task:

```yaml
- hosts: all
  roles:
    - role: BaxterStockman.packer
  tasks:
    - name: install cower
      packer:
        name: cower
        state: present
```

## Usage

Similar to the [pacman module][pacman-mod]. Note that package
status, removal, the corresponding `pacman` commands are used (`-Q`, `-R`,
respectively).

More detailed docs are on the way, but in general:

### Options

* `name`: Name of the AUR package(s) to install.  Accepts a single name or a
  list of names.  Optional.
* `state`: One of present, latest, or absent; whether the package should be
  installed, updated, or removed.  Optional; defaults to present.
* `upgrade`: One of yes or no; whether to upgrade all AUR packages.  Can be
  specified with `name` or run as its own task.  Optional; defaults to no.
* `recurse`: One of yes or no; whether to recursively remove packages. See the
  [pacman module docs][pacman-mod] for more.  Optional; defaults to no.

One of `name` or `upgrade` is required.

### Examples

```yaml
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
```

Have other ideas? Better way of doing something? Open an issue or a pull
request.

[packer]: https://github.com/keenerd/packer
[pacman-mod]: http://docs.ansible.com/pacman_module.html
