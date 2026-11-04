# WebGPU 与 WASM 后端选择

ONNX Runtime Web 支持两种执行后端：WebGPU 与 WASM。WebGPU 通过 GPU 并行执行矩阵运算，在批量推理时通常更快；WASM 在 CPU 上执行，兼容性最好，几乎所有现代浏览器都支持。

工程上应当在启动时探测后端：先检查 navigator.gpu 是否存在，再调用 requestAdapter() 真正申请适配器。只有拿到非空 adapter 才启用 WebGPU，否则自动降级到 WASM，并在界面中明确提示当前后端。

需要注意的是，某些环境暴露了 WebGPU API 但拿不到适配器（例如无 GPU 的无头浏览器、远程桌面），因此「有 API」不等于「能用」。更稳妥的做法是初始化后跑一次预热推理，如果失败再回落到 WASM，并记录降级原因。
