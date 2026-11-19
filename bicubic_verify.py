import random

def cr_w(f):
    f2, f3 = f*f, f*f*f
    return (-0.5*f3 +     f2 - 0.5*f,
             1.5*f3 - 2.5*f2        + 1.0,
            -1.5*f3 + 2.0*f2 + 0.5*f,
             0.5*f3 - 0.5*f2)

def taps(f):
    w0, w1, w2, w3 = cr_w(f)
    a, b = w0 + w1, w2 + w3
    s = w1 / a if abs(a) > 1e-6 else 0.0
    u = w3 / b if abs(b) > 1e-6 else 0.0
    return a, s, b, u

worst_sum = 0.0
worst_err = 0.0
for _ in range(20000):
    c = [random.uniform(-5, 5) for _ in range(4)]
    f = random.random()
    w = cr_w(f)
    worst_sum = max(worst_sum, abs(sum(w) - 1.0))
    ref = sum(wi*ci for wi, ci in zip(w, c))
    # emulate 2 bilinear taps
    a, s, b, u = taps(f)
    got = a*(c[0] + s*(c[1]-c[0])) + b*(c[2] + u*(c[3]-c[2]))
    worst_err = max(worst_err, abs(ref - got))

print("max |sum(w)-1| =", worst_sum)
print("max |cubic - 2tap| =", worst_err)

# 检查分母极小/为零的位置
for f in (0.0, 1e-7, 0.5, 1-1e-7, 1.0):
    print(f, ["%.6f" % x for x in cr_w(f)], "a,b =", "%.6f %.6f" % (cr_w(f)[0]+cr_w(f)[1], cr_w(f)[2]+cr_w(f)[3]))
