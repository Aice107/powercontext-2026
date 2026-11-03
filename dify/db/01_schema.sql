-- 《记仇客栈》seekdb 表结构
-- 目标版本：OceanBase seekdb v1.4.0.0（MySQL 协议，端口 2881）
-- 用途：应用数据层（玩家档案 / 恩怨账本 / 传闻 / 台词库 / 日报）
-- 检索能力：向量（HNSW, cosine）+ 全文（ngram，支持中文）+ 结构化过滤

CREATE DATABASE IF NOT EXISTS inn DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE inn;

DROP TABLE IF EXISTS inn_ledger;
DROP TABLE IF EXISTS inn_rumor;
DROP TABLE IF EXISTS inn_line;
DROP TABLE IF EXISTS inn_daily;
DROP TABLE IF EXISTS inn_player;

-- 玩家档案：仇值与访问统计的事实来源
CREATE TABLE inn_player (
  player_id     VARCHAR(64)  NOT NULL COMMENT '玩家标识 p_xxxx',
  nickname      VARCHAR(64)  NOT NULL DEFAULT '浪客',
  grudge        INT          NOT NULL DEFAULT 0 COMMENT '仇值 0-100',
  visits        INT          NOT NULL DEFAULT 0 COMMENT '住店次数',
  total_events  INT          NOT NULL DEFAULT 0 COMMENT '累计事件数',
  days_known    INT          NOT NULL DEFAULT 1 COMMENT '相识天数（跨天回访 +1）',
  last_session_id VARCHAR(64) NOT NULL DEFAULT '' COMMENT '最近一次会话，用于统计住店次数',
  created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_seen     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (player_id)
) COMMENT '玩家档案';

-- 恩怨账本：每一条恶作剧/善举
CREATE TABLE inn_ledger (
  id            BIGINT       NOT NULL AUTO_INCREMENT,
  player_id     VARCHAR(64)  NOT NULL,
  session_id    VARCHAR(64)  NOT NULL DEFAULT '',
  turn          INT          NOT NULL DEFAULT 0,
  action_text   VARCHAR(512) NOT NULL,
  action_type   VARCHAR(32)  NOT NULL DEFAULT 'other',
  severity      INT          NOT NULL DEFAULT 0,
  target        VARCHAR(64)  NOT NULL DEFAULT '',
  scene         VARCHAR(32)  NOT NULL DEFAULT '大堂',
  grudge_after  INT          NOT NULL DEFAULT 0,
  embedding     VECTOR(1024),
  created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_player_time (player_id, created_at),
  FULLTEXT KEY ft_action (action_text) WITH PARSER ngram
) COMMENT '恩怨账本';

CREATE VECTOR INDEX vidx_ledger ON inn_ledger(embedding) WITH (distance=cosine, type=hnsw);

-- 传闻：由高严重度事件派生，供其它场景引用
CREATE TABLE inn_rumor (
  id             BIGINT       NOT NULL AUTO_INCREMENT,
  player_id      VARCHAR(64)  NOT NULL,
  source_event_id BIGINT      NOT NULL DEFAULT 0,
  rumor_text     VARCHAR(512) NOT NULL,
  spread         INT          NOT NULL DEFAULT 1,
  scene          VARCHAR(32)  NOT NULL DEFAULT '地窖',
  embedding      VECTOR(1024),
  created_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_player (player_id),
  FULLTEXT KEY ft_rumor (rumor_text) WITH PARSER ngram
) COMMENT '传闻';

CREATE VECTOR INDEX vidx_rumor ON inn_rumor(embedding) WITH (distance=cosine, type=hnsw);

-- 台词库：给 LLM 提供语气锚点，防止出戏（只做检索素材，不做决策）
CREATE TABLE inn_line (
  id     BIGINT       NOT NULL AUTO_INCREMENT,
  npc    VARCHAR(32)  NOT NULL DEFAULT '柳三娘',
  scene  VARCHAR(32)  NOT NULL DEFAULT '大堂',
  tier   INT          NOT NULL DEFAULT 0 COMMENT '档位 0-4',
  tone   VARCHAR(32)  NOT NULL DEFAULT 'plain',
  text   VARCHAR(512) NOT NULL,
  PRIMARY KEY (id),
  KEY idx_tier (tier),
  FULLTEXT KEY ft_line (text) WITH PARSER ngram
) COMMENT '台词库';

-- 日报：打烊结算的聚合缓存
CREATE TABLE inn_daily (
  player_id  VARCHAR(64)  NOT NULL,
  day        DATE         NOT NULL,
  events     INT          NOT NULL DEFAULT 0,
  delta      INT          NOT NULL DEFAULT 0,
  top_type   VARCHAR(32)  NOT NULL DEFAULT '',
  summary    VARCHAR(512) NOT NULL DEFAULT '',
  PRIMARY KEY (player_id, day)
) COMMENT '日报';
