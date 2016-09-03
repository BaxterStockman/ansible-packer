# TODO

- Unhelpful output for bad package names (`j2` does not exist):

```
localhost | FAILED! => {
  "changed": false,
  "failed": true,
  "msg": "failed to install package j2, because: stty: 'standard
  input': Inappropriate ioctl for device\n"
}
```
