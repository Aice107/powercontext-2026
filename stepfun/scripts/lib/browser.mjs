// 浏览器启动参数（基准/冒烟/UI 流程共用）。
// 本机无 GPU 时通过 SwiftShader 的 Vulkan ICD 让 Chromium 暴露一个软件 WebGPU 适配器，
// 这样 WebGPU 代码路径也能被真实执行与测量。
import { existsSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

export function chromiumPath() {
  if (process.env.CHROME_PATH) return process.env.CHROME_PATH;
  const cache = join(homedir(), '.cache', 'ms-playwright');
  for (const dir of ['chromium-1148', 'chromium-1134', 'chromium-1129']) {
    const candidate = join(cache, dir, 'chrome-linux', 'chrome');
    if (existsSync(candidate)) return candidate;
  }
  return undefined;
}

export function swiftshaderIcd() {
  const exe = chromiumPath();
  if (!exe) return undefined;
  const icd = join(exe.replace(/\/chrome$/, ''), 'vk_swiftshader_icd.json');
  return existsSync(icd) ? icd : undefined;
}

export function launchOptions({ headed = false } = {}) {
  const icd = swiftshaderIcd();
  const env = { ...process.env };
  if (icd) env.VK_ICD_FILENAMES = icd;
  return {
    headless: !headed,
    executablePath: chromiumPath(),
    env,
    args: [
      '--no-sandbox',
      '--enable-unsafe-webgpu',
      '--enable-unsafe-swiftshader',
      '--enable-features=Vulkan',
      '--use-vulkan=swiftshader',
    ],
  };
}
