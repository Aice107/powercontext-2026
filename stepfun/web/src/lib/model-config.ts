// 端侧模型配置：模型来源、版本、量化档位与本地/远端加载路径。
export const MODEL_ID = 'bge-small-zh-v1.5';
export const MODEL_REMOTE_REPO = 'Xenova/bge-small-zh-v1.5';
export const MODEL_VERSION = 'Xenova/bge-small-zh-v1.5@main (bge-small-zh-v1.5, ONNX)';
export const MODEL_DIM = 512;

export type Dtype = 'q8' | 'fp16' | 'fp32';

export interface DtypeInfo {
  id: Dtype;
  label: string;
  file: string;
  note: string;
}

export const DTYPES: Record<Dtype, DtypeInfo> = {
  q8: { id: 'q8', label: 'INT8 (q8)', file: 'onnx/model_quantized.onnx', note: 'ONNX Runtime 动态量化：权重 INT8，激活动态量化' },
  fp16: { id: 'fp16', label: 'FP16', file: 'onnx/model_fp16.onnx', note: '权重半精度（WebGPU 首选）' },
  fp32: { id: 'fp32', label: 'FP32 基线', file: 'onnx/model.onnx', note: '未量化基线，用于体积/质量对照' },
};

// 本地模型目录由服务端 /models 提供（npm run fetch-models 下载），远端回退到 hf-mirror
export const LOCAL_MODEL_PATH = '/models/';
export const REMOTE_HOST = 'https://hf-mirror.com';

export const DEFAULT_TOP_K = 5;
export const DEFAULT_CHUNK_SIZE = 320;
export const DEFAULT_CHUNK_OVERLAP = 64;
