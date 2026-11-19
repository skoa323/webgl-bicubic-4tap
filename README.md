# webgl-bicubic-4tap

WebGL2 / GLSL ES 3.00 上用手写 bicubic 替代双线性放大，4 次纹理采样完成 2D 三次卷积。

用于：3D 家装实时渲染引擎里瓷砖 / 木纹 / 法线贴图的放大，以及 lightmap atlas；
双线性在 2–3 倍放大时细纹出现方块状伪影与摩尔纹。

## 核心恒等式

把 catmull-rom 的 4 个 cubic 权重两两合并，每段交给硬件双线性一次取完：

```
w0*c0 + w1*c1  ≡  (w0+w1) * mix(c0, c1, w1/(w0+w1))
w2*c2 + w3*c3  ≡  (w2+w3) * mix(c2, c3, w3/(w2+w3))
```

两轴各 2 段 → 4 次采样 = 2D 三次卷积。采样数 16 → 4。
数值验证：`bicubic_verify.py`，2 万组随机构型，重建误差 ~1e-15，权重和恒为 1。

## 两个必须知道的前提

1. **纹理必须 LINEAR + CLAMP_TO_EDGE。** 这是正确性条件，不是性能选项 —— 4-tap 的
   全部意义就是把插值交给硬件，用 NEAREST 会直接退化。
2. **`f == 0` 与 `f == 1` 是两个 0/0 死点。** `w0+w1` 和 `w2+w3` 分别在那里归零，
   不挡就是一个 NaN 顺着 clamp 变成整条黑边。

## 硬打包与 4-tap 在原理上互斥

RGBA8 存 half（位运算打包）必须 NEAREST，因为硬件 LINEAR 插的是打包后的字节而不是
解出来的浮点值，结果全是噪声。想同时要低带宽和大放大，只剩两条路：

- 换成可线性插值的编码：RGBM / 8bit LogLuv / 共享指数，误差 1–3%，保住 4 tap；
- 硬打包 + NEAREST + 手动双线性 → 每轴 4 次、2D 共 16 次，退化成暴力版。

目标机型（Mali-G52/G57、Adreno 610/619）没有可靠 renderable float，
所以这个取舍绕不过去，先测方案一的误差能不能进 golden diff 阈值。

## 文件

- `bicubic.glsl` — `crAxisWeights()` 权重分解、`texBicubic()` 四抽样、B-spline 无过冲变体、half/RGBA8 pack-unpack
- `bicubic_verify.py` — CPU 侧恒等式与边界验算，可直接当 oracle

## 参考

Catmull-Rom cubic convolution，a = -0.5。B-spline 变体权重恒正、无 ringing，代价是糊约一纹素。
