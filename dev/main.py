def bf_init(m):
    return [0] * m


def h1(s, m):
    h = 0
    for ch in s:
        h = (h * 131 + ord(ch)) % m
    return h


def h2(s, m):
    h = 0
    for ch in s:
        h = (h * 137 + ord(ch)) % m
    return h


def bf_add(b, s):
    b[h1(s, len(b))] = 1
    b[h2(s, len(b))] = 1


def bf_check(b, s):
    return bool(b[h1(s, len(b))] and b[h2(s, len(b))])


B = bf_init(100000)
bf_add(B, "apple")
print(bf_check(B, "apple"))
print(bf_check(B, "orange"))
