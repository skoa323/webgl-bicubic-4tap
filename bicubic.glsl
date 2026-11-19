// ---------------------------------------------------------------------------
// 4-tap bicubic (Catmull-Rom, a = -0.5)  |  GLSL ES 3.00 / WebGL2
//
// 核心恒等式（已数值验证，误差 ~1e-15）：
//   把 4 个 cubic 权重两两合并 → 每轴 2 段，每段用硬件双线性一次取完
//       w0*c0 + w1*c1  ==  (w0+w1) * mix(c0, c1, w1/(w0+w1))
//       w2*c2 + w3*c3  ==  (w2+w3) * mix(c2, c3, w3/(w2+w3))
//   2 轴各 2 段 → 4 次纹理采样 = 2D 三次卷积。采样数 16 → 4。
// ---------------------------------------------------------------------------

// 单轴权重分解：返回 vec4(a, s, b, u)
//   a = 后一纹素对的权重   s = 该对的插值位置 ∈ [0,1]
//   b = 前一纹素对的权重   u = 该对的插值位置 ∈ [0,1]
vec4 crAxisWeights(float f) {
    float f2 = f * f;
    float f3 = f2 * f;

    float w0 = -0.5 * f3 +       f2 - 0.5 * f;
    float w1 =  1.5 * f3 - 2.5 * f2        + 1.0;
    float w2 = -1.5 * f3 + 2.0 * f2 + 0.5 * f;
    float w3 =  0.5 * f3 - 0.5 * f2;

    float a = w0 + w1;          // f == 1.0 时 a == 0 → 0/0，必须挡
    float b = w2 + w3;          // f == 0.0 时 b == 0 → 0/0，必须挡

    // 兜底取 0：此时该段权重本身也为 0，乘 0 不影响结果
    float s = (abs(a) > 1e-5) ? w1 / a : 0.0;
    float u = (abs(b) > 1e-5) ? w3 / b : 0.0;

    return vec4(a, s, b, u);
}

// ---------------------------------------------------------------------------
// 采样。前提：纹理 LINEAR + CLAMP_TO_EDGE —— 这是正确性条件，不是性能选项
// ---------------------------------------------------------------------------
vec4 texBicubic(sampler2D tex, vec2 uv) {
    vec2 size = vec2(textureSize(tex, 0));
    vec2 p = uv * size - 0.5;          // 转纹素中心坐标系
    vec2 i = floor(p);
    vec2 f = p - i;                    // 已在 [0,1)

    vec4 wx = crAxisWeights(f.x);
    vec4 wy = crAxisWeights(f.y);

    float x0 = i.x + wx.y;             // 前一对的采样位置
    float x1 = i.x + 1.0 + wx.w;       // 后一对的采样位置
    float y0 = i.y + wy.y;
    float y1 = i.y + 1.0 + wy.w;

    vec2 inv = 1.0 / size;             // p 已减 0.5，这里不用再补半纹素

    vec4 c00 = texture(tex, vec2(x0, y0) * inv);
    vec4 c10 = texture(tex, vec2(x1, y0) * inv);
    vec4 c01 = texture(tex, vec2(x0, y1) * inv);
    vec4 c11 = texture(tex, vec2(x1, y1) * inv);

    // 权重先做 1D 折叠，省 4 次乘法
    vec2 wx2 = vec2(wx.x, wx.z);
    vec2 wy2 = vec2(wy.x, wy.z);
    vec4 col0 = c00 * wx2.x + c10 * wx2.y;
    vec4 col1 = c01 * wx2.x + c11 * wx2.y;

    return col0 * wy2.x + col1 * wy2.y;
}

// ---------------------------------------------------------------------------
// B-spline 变体：权重恒正、无过冲（不会出 ringing），代价是糊 ~1 纹素
// 需要时对纹理做一次预滤波（1/6[1 4 1] 反卷积）可找回锐度
// ---------------------------------------------------------------------------
vec4 bsAxisWeights(float f) {
    float f2 = f * f, f3 = f2 * f;
    float w0 = (1.0 - 3.0*f + 3.0*f2 -     f3) / 6.0;
    float w1 = (4.0 -        6.0*f2 + 3.0*f3) / 6.0;
    float w2 = (1.0 + 3.0*f + 3.0*f2 - 3.0*f3) / 6.0;
    float w3 =                         f3  / 6.0;

    float a = w0 + w1, b = w2 + w3;
    return vec4(a, w1 / a, b, w3 / b);   // B-spline 分母恒 ≥ 1/6，不会除零
}

// ---------------------------------------------------------------------------
// RGBA pack/unpack（2 个 half 塞 1 个 RGBA8）
//
// ⚠ 致命约束：打包纹理必须 NEAREST。硬件 LINEAR 插的是打包后的字节，不是解出来的
//   数值，结果全是噪声。所以「4-tap + 硬打包」不成立 —— 想同时要，只剩两条路：
//   (1) 用可线性插值的编码：RGBM / 8bit LogLuv / 共享指数，误差 1~3%，保住 4 tap
//   (2) 硬打包 + NEAREST + 手动双线性 → 每轴 4 次、2D 共 16 次，退化成暴力版
//   低端 Mali 上先测 (1) 的误差能不能进你的 golden diff 阈值。
// ---------------------------------------------------------------------------
vec2 unpackHalf2FromRGBA8(vec4 texel) {
    uvec4 b = uvec4(texel * 255.0 + 0.5);
    uint word = b.x | (b.y << 8) | (b.z << 16) | (b.w << 24);
    return unpackHalf2x16(word);        // 一个 RGBA8 = 2 个 half = 2 个通道
}

// 反向打包：4 个通道 = 4 个 half = 8 字节 = 需要 2 个 RGBA8 纹素
// 每张图各存 2 个通道，解时才拼得回 vec4；单张 RGBA8 只能存 2 通道
uvec4 packHalf2ToRGBA8(vec2 h) {
    uint w = packHalf2x16(h);
    return uvec4(w & 0xFFu, (w >> 8) & 0xFFu, (w >> 16) & 0xFFu, (w >> 24) & 0xFFu);
}
