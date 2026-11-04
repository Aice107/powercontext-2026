# WASM 多线程与跨源隔离

ONNX Runtime Web 的 WASM 后端在多线程模式下使用 SharedArrayBuffer，而浏览器只在「跨源隔离」（cross-origin isolated）的页面中开放 SharedArrayBuffer。要启用跨源隔离，服务端需要返回两个响应头：Cross-Origin-Opener-Policy: same-origin 与 Cross-Origin-Embedder-Policy: require-corp。

开启之后，页面加载跨源资源需要对方提供 CORP 或 CORS 头，因此模型权重、运行时 wasm 最好放在同源静态目录，避免被 COEP 拦截。

如果没有这两个头，运行时通常会自动退回单线程，功能不受影响，但吞吐会下降。技术说明中应当写清楚是否启用了多线程，以及线程数配置。
