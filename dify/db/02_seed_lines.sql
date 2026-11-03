-- 扩充版台词库：5 档 × 10 个高频道具，用作 LLM 语气锚点（只做检索素材，不做判定）
USE inn;
DELETE FROM inn_line;

-- T0
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','后厨',0,'t0','这坛酒是去年秋里埋的，您尝尝，不够我再添。');
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','大堂',0,'t0','账本我给您留着空行，住得舒坦比什么都强。');
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','大堂',0,'t0','靠窗那张桌子干净，您坐那儿亮堂。');
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','后厨',0,'t0','醋我拌了蒜，蘸饺子正好，您要不来一碟？');
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','客房',0,'t0','屋顶前儿刚补过，夜里下雨不打紧。');
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','大堂',0,'t0','客人不多，正好安静，您慢慢吃。');
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','后厨',0,'t0','灶上留着盘酱牛肉，温着，您要不要来两块？');
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','客房',0,'t0','行李我让小二送上楼，您轻省着走。');
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','后院',0,'t0','柴房堆得满，夜里冷的话我给您多添床被。');
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','大堂',0,'t0','房钱不急，走时一起算就成。');

-- T1
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','后厨',1,'t1','这坛酒……先付钱，我这人记性不好，账记得清。');
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','大堂',1,'t1','账本您别碰，那上头写的都是我这份家业。');
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','大堂',1,'t1','桌子别挪，底下垫着我自己的钱。');
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','后厨',1,'t1','醋坛盖着，您手别往里伸。');
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','客房',1,'t1','屋顶上有瓦，您上去可别踩坏了。');
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','大堂',1,'t1','客人是来看我这张脸的，不是来看您的。');
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','后厨',1,'t1','酱牛肉在灶上，我数过的，别拿。');
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','客房',1,'t1','行李放柜上，丢了我不赔。');
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','后院',1,'t1','柴房是给柴睡的，不是给客官睡的。');
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','大堂',1,'t1','房钱涨了，涨多少看您今天表现。');

-- T2
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','后厨',2,'t2','酒还热着，人可凉了。您慢慢喝。');
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','大堂',2,'t2','账本我收进匣子里了，往后不摆外头。');
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','大堂',2,'t2','别坐那桌，那桌我刚擦过。');
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','后厨',2,'t2','醋坛子我上了锁，钥匙在袖子里。');
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','客房',2,'t2','屋里漏不漏，您就别操心了。');
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','大堂',2,'t2','客人走了两个，我倒省一口饭。');
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','后厨',2,'t2','灶上没有牛肉了，您将就吃点青菜。');
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','客房',2,'t2','行李搁门房，别放我柜台上。');
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','后院',2,'t2','柴房门开着，您自己看，没别的东西。');
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','大堂',2,'t2','房钱翻倍，您嫌贵可以另找别家。');

-- T3
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','后厨',3,'t3','您的酒——兑了点井水，天热，败火。');
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','大堂',3,'t3','账本我另抄了一本，写得不客气。');
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','大堂',3,'t3','桌子腿我锯短了半寸，您掀的时候留神。');
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','后厨',3,'t3','醋坛里放了点料，您要是洗手，手会痒。');
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','客房',3,'t3','夜里要是听见屋顶响，别起来，是我在修瓦。');
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','大堂',3,'t3','客人我也打了招呼，让他们绕开您这号人。');
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','后厨',3,'t3','牛肉我另添了盐，您就当补身子。');
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','客房',3,'t3','行李我挪柴房去了，那儿凉快。');
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','后院',3,'t3','柴房门上我挂了铃铛，谁进去我知道。');
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','大堂',3,'t3','房钱按三倍算，账上写得明白。');

-- T4
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','后厨',4,'t4','这坛酒您别碰了，您喝了也是浪费我的水。');
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','大堂',4,'t4','账本记到最后一页了，写的是您。');
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','大堂',4,'t4','桌子我认了，钱您照赔。');
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','后厨',4,'t4','醋坛的钱也算在您头上。');
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','客房',4,'t4','屋顶我自己修，不用您的人情。');
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','大堂',4,'t4','客人我拦回来了，您这脸他们不必再看。');
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','后厨',4,'t4','灶上不留您的份。');
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','客房',4,'t4','行李我让伙计收拾齐整搁在门房，一样不少。');
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','后院',4,'t4','柴房不必去了，您连柴房也住不得。');
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','大堂',4,'t4','账按双倍结，柜上现银，今日天黑前出门。');

-- 善举/和解专用（对账时的别扭原谅）
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','客房',0,'kind','我这屋顶，你还真修上去了？行了，喝口热的，别忙着走。');
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','大堂',0,'kind','账我不催你，你也别老惦记那点旧事。');
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','后厨',0,'kind','锅里有汤，自己盛。别客气，客气我反而不习惯。');
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','大堂',0,'kind','你这个人，坏是坏，倒还有点良心。');
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','客房',1,'kind','屋顶修得还行吧…这回算你有心。');
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','大堂',1,'kind','赔的钱我收了，账上抹一笔，别的事另说。');
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','后厨',1,'kind','帮我把这筐菜择了，择完再说你的账。');
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','大堂',1,'kind','伸手不打笑脸人，你今儿这副样子，我倒不好开口。');
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','后院',1,'kind','柴你也劈了，水你也挑了，我还能说什么。');
INSERT INTO inn_line (npc, scene, tier, tone, text) VALUES ('柳三娘','大堂',1,'kind','一句软话就想抵三笔旧账？…行吧，先记着。');
