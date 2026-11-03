-- 演示数据：一个已经"恶名在外"的玩家，供评审核对 T1~T3 档位的表现
-- 说明：p_demo01 的仇值被预置为 62（T3 报复档），评审可直接用该 player_id 体验
USE inn;

DELETE FROM inn_ledger WHERE player_id = 'p_demo01';
DELETE FROM inn_rumor  WHERE player_id = 'p_demo01';
DELETE FROM inn_player WHERE player_id = 'p_demo01';

INSERT INTO inn_player (player_id, nickname, grudge, visits, total_events, days_known, last_session_id, created_at, last_seen)
VALUES ('p_demo01', '陈三', 62, 4, 7, 3, '', DATE_SUB(NOW(), INTERVAL 3 DAY), DATE_SUB(NOW(), INTERVAL 1 DAY));

-- 7 条历史事件（时间跨 3 天），grudge_after 与实际累加一致
INSERT INTO inn_ledger (player_id, session_id, turn, action_text, action_type, severity, target, scene, grudge_after, created_at) VALUES
('p_demo01','conv_demo_1', 2, '往酒坛里兑了半坛井水',      'drink',     2, '酒坛',  '后厨',  12, DATE_SUB(NOW(), INTERVAL 3 DAY)),
('p_demo01','conv_demo_1', 5, '偷吃了灶上留的酱牛肉',      'food',      2, '酱牛肉','后厨',  26, DATE_SUB(NOW(), INTERVAL 3 DAY)),
('p_demo01','conv_demo_2', 1, '在她账本上画了只乌龟',      'property',  3, '账本',  '大堂',  47, DATE_SUB(NOW(), INTERVAL 2 DAY)),
('p_demo01','conv_demo_2', 4, '半夜在屋顶学猫叫',          'noise',     2, '屋顶',  '客房',  61, DATE_SUB(NOW(), INTERVAL 2 DAY)),
('p_demo01','conv_demo_3', 2, '在醋坛子里洗了手',          'hygiene',   3, '醋坛',  '后厨',  61, DATE_SUB(NOW(), INTERVAL 1 DAY)),
('p_demo01','conv_demo_3', 6, '吓跑了两个住店的客人',      'guest',     4, '住客',  '大堂',  62, DATE_SUB(NOW(), INTERVAL 1 DAY)),
('p_demo01','conv_demo_3', 7, '掀了半张桌子',              'violence',  5, '桌子',  '大堂',  62, DATE_SUB(NOW(), INTERVAL 1 DAY));

-- 传闻（由高严重度事件派生）
INSERT INTO inn_rumor (player_id, source_event_id, rumor_text, spread, scene, created_at) VALUES
('p_demo01', 6, '地窖里都在传，那位姓陈的客官把住店的都吓跑了，一夜之间没人敢上楼。', 3, '地窖', DATE_SUB(NOW(), INTERVAL 1 DAY)),
('p_demo01', 7, '大堂的桌子被掀了半张，小二说那人跟三娘瞪了半宿的眼。', 2, '大堂', DATE_SUB(NOW(), INTERVAL 1 DAY));

-- ---------------------------------------------------------------
-- 档位梯度演示：同一句话在不同仇值下的态度差异（S8 用）
-- p_tier1 仇值 28（T1 戒备）／p_tier2 仇值 48（T2 冷脸）
DELETE FROM inn_ledger WHERE player_id IN ('p_tier1','p_tier2');
DELETE FROM inn_player WHERE player_id IN ('p_tier1','p_tier2');

INSERT INTO inn_player (player_id, nickname, grudge, visits, total_events, days_known, last_session_id, created_at, last_seen)
VALUES ('p_tier1', '白小乙', 28, 2, 2, 2, '', DATE_SUB(NOW(), INTERVAL 2 DAY), DATE_SUB(NOW(), INTERVAL 1 DAY)),
       ('p_tier2', '赵九',   48, 3, 3, 2, '', DATE_SUB(NOW(), INTERVAL 2 DAY), DATE_SUB(NOW(), INTERVAL 1 DAY));

INSERT INTO inn_ledger (player_id, session_id, turn, action_text, action_type, severity, target, scene, grudge_after, created_at) VALUES
('p_tier1','conv_t1', 3, '往酒坛里兑了半壶水',  'drink',    2, '酒坛', '后厨', 14, DATE_SUB(NOW(), INTERVAL 2 DAY)),
('p_tier1','conv_t1', 6, '半夜在屋顶学猫叫',    'noise',    2, '屋顶', '客房', 28, DATE_SUB(NOW(), INTERVAL 1 DAY)),
('p_tier2','conv_t2', 2, '偷吃了灶上的酱牛肉',  'food',     2, '酱牛肉','后厨', 14, DATE_SUB(NOW(), INTERVAL 2 DAY)),
('p_tier2','conv_t2', 5, '在她账本上画了只乌龟','property', 3, '账本', '大堂', 35, DATE_SUB(NOW(), INTERVAL 2 DAY)),
('p_tier2','conv_t2', 9, '把客人的酒换成了醋',  'drink',    2, '酒壶', '大堂', 48, DATE_SUB(NOW(), INTERVAL 1 DAY));
