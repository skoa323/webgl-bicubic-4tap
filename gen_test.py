#!/usr/bin/env python3
"""把 bicubic.glsl 注入一个可跑的真机 WebGL2 测试页。"""
import pathlib

WS = pathlib.Path(__file__).parent
glsl = (WS / "bicubic.glsl").read_text()

frag = """#version 300 es
precision highp float;
precision highp sampler2D;
uniform sampler2D uTex;
uniform vec2 uSize;      // canvas 尺寸
out vec4 fragColor;
""" + glsl + """
void main() {
    vec2 uv = gl_FragCoord.xy / uSize;
    fragColor = texBicubic(uTex, uv);
}
"""

vert = """#version 300 es
in vec2 aPos;
void main() { gl_Position = vec4(aPos, 0.0, 1.0); }
"""

html = """<!doctype html>
<meta charset="utf-8">
<title>bicubic 4tap / WebGL2 真机验证</title>
<style>
 body{font:14px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace;background:#111;color:#ddd;padding:16px}
 #out{white-space:pre-wrap}
 .ok{color:#4ade80}.bad{color:#f87171}.warn{color:#fbbf24}
 canvas{image-rendering:pixelated;width:320px;height:320px;border:1px solid #444}
</style>
<div id="out">running…</div>
<canvas id="c" width="64" height="64"></canvas>
<script>
const FRAG = `__FRAG__`;
const VERT = `__VERT__`;
const out = document.getElementById('out');
const log = [];
const say = (s, cls) => { log.push((cls?`<span class="${cls}">`:'')+s+(cls?'</span>':'')); out.innerHTML = log.join('\\n'); };

const cv = document.getElementById('c');
const gl = cv.getContext('webgl2', {antialias:false, preserveDrawingBuffer:true});
if (!gl) { say('FATAL: 没有 webgl2 上下文','bad'); window.__RESULT__={ok:false,reason:'no webgl2'}; }
else {
  const dbg = gl.getExtension('WEBGL_debug_renderer_info');
  say('RENDERER: ' + (dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER)));
  say('VENDOR  : ' + (dbg ? gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL) : gl.getParameter(gl.VENDOR)));
  say('VERSION : ' + gl.getParameter(gl.VERSION));
  say('SL     : ' + gl.getParameter(gl.SHADING_LANGUAGE_VERSION));

  function sh(type, src, name) {
    const s = gl.createShader(type);
    gl.shaderSource(s, src); gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
      const l = gl.getShaderInfoLog(s);
      say('COMPILE FAIL ' + name + '\\n' + l, 'bad');
      window.__SHADER_LOG__ = l;
      throw new Error(name + ': ' + l);
    }
    return s;
  }

  let prog;
  try {
    prog = gl.createProgram();
    gl.attachShader(prog, sh(gl.VERTEX_SHADER, VERT, 'vert'));
    gl.attachShader(prog, sh(gl.FRAGMENT_SHADER, FRAG, 'frag'));
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
      const l = gl.getProgramInfoLog(prog);
      say('LINK FAIL\\n' + l, 'bad'); throw new Error('link: ' + l);
    }
    say('编译/链接: OK (0 error)', 'ok');
    window.__SHADER_LOG__ = '';
  } catch(e) {
    say('shader stage failed, stop.', 'bad');
    window.__RESULT__ = {ok:false, reason:'compile', log:window.__SHADER_LOG__};
  }

  if (prog) {
    // ---- 测试纹理：8x8，确定性伪随机 ----
    const N = 8, data = new Uint8Array(N*N*4);
    let seed = 12345;
    const rnd = () => (seed = (seed*1103515245 + 12345) & 0x7fffffff) / 0x7fffffff;
    for (let i=0;i<N*N*4;i++) data[i] = Math.floor(rnd()*256);
    const tex = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, tex);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, N, N, 0, gl.RGBA, gl.UNSIGNED_BYTE, data);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);

    const vao = gl.createVertexArray();
    gl.bindVertexArray(vao);
    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1, 3,-1, -1,3]), gl.STATIC_DRAW);
    const loc = gl.getAttribLocation(prog, 'aPos');
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);

    gl.useProgram(prog);
    gl.uniform1i(gl.getUniformLocation(prog,'uTex'), 0);
    gl.uniform2f(gl.getUniformLocation(prog,'uSize'), cv.width, cv.height);
    gl.viewport(0,0,cv.width,cv.height);
    gl.clearColor(0,0,0,1); gl.clear(gl.COLOR_BUFFER_BIT);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    const px = new Uint8Array(cv.width*cv.height*4);
    gl.readPixels(0,0,cv.width,cv.height,gl.RGBA,gl.UNSIGNED_BYTE,px);

    // ---- CPU 参考：同样的数学，浮点 ----
    const crW = f => {
      const f2=f*f, f3=f2*f;
      const w0=-0.5*f3+f2-0.5*f, w1=1.5*f3-2.5*f2+1, w2=-1.5*f3+2*f2+0.5*f, w3=0.5*f3-0.5*f2;
      const a=w0+w1, b=w2+w3;
      return [a, Math.abs(a)>1e-5?w1/a:0, b, Math.abs(b)>1e-5?w3/b:0];
    };
    const texel = (x,y,ch) => {
      x = Math.min(N-1, Math.max(0, x)); y = Math.min(N-1, Math.max(0, y));
      return data[(y*N+x)*4+ch] / 255;
    };
    const bilin = (x,y,ch) => {   // x,y 是纹素中心坐标
      const p = x-0.5, q = y-0.5;
      const i=Math.floor(p), j=Math.floor(q);
      const fx=p-i, fy=q-j;
      const v00=texel(i,j,ch), v10=texel(i+1,j,ch), v01=texel(i,j+1,ch), v11=texel(i+1,j+1,ch);
      return (v00+(v10-v00)*fx)*(1-fy) + (v01+(v11-v01)*fx)*fy;
    };
    let maxErr = 0, sumErr = 0, cnt = 0, worst = null;
    for (let y=0;y<cv.height;y++) for (let x=0;x<cv.width;x++) {
      const uvx = (x+0.5)/cv.width, uvy=(y+0.5)/cv.height;
      const px_ = uvx*N-0.5, py_ = uvy*N-0.5;
      const ix=Math.floor(px_), iy=Math.floor(py_);
      const wx = crW(px_-ix), wy = crW(py_-iy);
      const xs = [ix+wx[1], ix+1+wx[3]], ys = [iy+wy[1], iy+1+wy[3]];
      const wxs = [wx[0], wx[2]], wys=[wy[0], wy[2]];
      for (let ch=0;ch<4;ch++) {
        let ref=0;
        for (let a2=0;a2<2;a2++) for (let b2=0;b2<2;b2++)
          ref += wxs[a2]*wys[b2]*bilin(xs[a2], ys[b2], ch);
        ref = Math.min(1, Math.max(0, ref));
        const got = px[((y)*cv.width+x)*4+ch]/255;  // readPixels 是自下而上
        const e = Math.abs(ref-got);
        sumErr += e; cnt++;
        if (e > maxErr) { maxErr = e; worst = {x,y,ch,ref,got}; }
      }
    }
    const maxLSB = maxErr*255, avgLSB = (sumErr/cnt)*255;
    say('');
    say('CPU(float) 参考 vs GPU(RGBA8) 输出，64x64 共 ' + cnt + ' 个分量:');
    say('  max |err| = ' + maxErr.toFixed(6) + '  (' + maxLSB.toFixed(2) + ' LSB)',
        maxLSB > 4 ? 'bad' : 'ok');
    say('  avg |err| = ' + (sumErr/cnt).toFixed(6) + '  (' + avgLSB.toFixed(3) + ' LSB)');
    if (worst) say('  worst @ ' + JSON.stringify(worst));
    say('');
    say(maxLSB <= 4 ? '判定: PASS（8-bit 量化下允许 ≤4 LSB）' : '判定: FAIL',
        maxLSB <= 4 ? 'ok' : 'bad');

    // ---- 双线性对照：同一位置，看差异有多大（证明真的不是双线性） ----
    let dmax = 0;
    for (let y=0;y<cv.height;y++) for (let x=0;x<cv.width;x++) {
      const uvx=(x+0.5)/cv.width*N, uvy=(y+0.5)/cv.height*N;
      for (let ch=0;ch<4;ch++) {
        const l = bilin(uvx, uvy, ch);
        const b = px[((y)*cv.width+x)*4+ch]/255;
        dmax = Math.max(dmax, Math.abs(l-b));
      }
    }
    say('对照：与纯双线性的最大偏差 = ' + (dmax*255).toFixed(1) + ' LSB（应显著 > 0，否则说明退化成双线性）',
        dmax*255 > 5 ? 'ok' : 'warn');

    window.__RESULT__ = {ok: maxLSB<=4, maxLSB, avgLSB, diffFromBilinear: dmax*255,
                         renderer: dbg?gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL):gl.getParameter(gl.RENDERER),
                         shaderLog: window.__SHADER_LOG__};
    say('');
    say('DONE', 'ok');
  }
}
</script>
"""

html = html.replace("__FRAG__", frag).replace("__VERT__", vert)
(WS / "test.html").write_text(html)
print("wrote test.html", len(html), "bytes")
