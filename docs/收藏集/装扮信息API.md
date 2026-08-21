## 主题装扮信息API

> https://api.bilibili.com/x/garb/v2/mall/suit/detail

*请求方式: GET*

**URL参数:**

| 参数名  | 类型 | 内容         | 必要性 | 备注 |
| ------- | ---- | ------------ | ------ | ---- |
| buvid   | str  | 设备唯一标识 | 不必要 |      |
| csrf    | str  | 用户csrf     | 不必要 |      |
| from    | str  | 来源页面     | 不必要 |      |
| from_id | int  | 来源页面id   | 不必要 |      |
| item_id | int  | 装扮id       | 必要   |      |
| part    | str  | ?分类        | 不必要 |      |

**JSON回复:**

根对象：

| 字段    | 类型 | 内容     | 备注                        |
| ------- | ---- | -------- | --------------------------- |
| code    | num  | 返回值   | `0`：成功<br />`-400`：错误 |
| message | str  | 错误信息 |                             |
| ttl     | num  | 1        |                             |
| data    | obj  | 信息本体 |                             |

`data` 对象：

| 字段              | 类型 | 内容         | 备注             |
| ----------------- | ---- | ------------ | ---------------- |
| item_id           | num  | 装扮id       |                  |
| name              | str  | 装扮名称     |                  |
| group_id          | num  | 分组id       |                  |
| group_name        | str  | 分组名称     |                  |
| part_id           | num  | 分类id       |                  |
| state             | str  | 状态         |                  |
| properties        | obj  | 装扮具体属性 |                  |
| current_activity  | str  | 当前活动     |                  |
| next_activity     | obj  | 下一个活动   |                  |
| current_sources   | str  |              | **作用尚不明确** |
| finish_sources    | str  |              | **作用尚不明确** |
| sale_left_time    | num  |              | **作用尚不明确** |
| sale_time_end     | num  |              | **作用尚不明确** |
| sale_surplus      | num  | 商品剩余数量 |                  |
| sale_count_desc   | str  | 促销销量说明 |                  |
| total_count_desc  | str  | 总销量说明   |                  |
| tag               | str  | 标签         |                  |
| jump_link         | str  | 跳转链接     |                  |
| sales_mode        | num  | 促销模式     |                  |
| suit_items        | obj  | 装扮具体内容 |                  |
| fan_user          | obj  | 装扮来源用户 |                  |
| unlock_items      | obj  | 未解锁装扮   |                  |
| activity_entrance | obj  | 活动入口     |                  |

`properties` 对象：

| 字段                       | 类型 | 内容                        | 备注                                                |
| -------------------------- | ---- | --------------------------- | --------------------------------------------------- |
| desc                       | str  | 说明                        |                                                     |
| fan_desc                   | str  | 用户说明                    |                                                     |
| fan_id                     | str  | 装扮id                      | 获取到的数据，有时候是数字文本，有时候是普通文本    |
| fan_item_ids               | str  | 装扮id列表                  |                                                     |
| fan_mid                    | str  | 用户mid                     |                                                     |
| fan_no_color               | str  |                             | **为一串颜色16进制字符串，但作用尚不明确**          |
| fan_recommend_desc         | str  | 用户推荐说明                |                                                     |
| fan_recommend_jump_type    | str  | 跳转类型                    |                                                     |
| fan_recommend_jump_value   | str  | 跳转的值                    | 一般为该装扮所有者的个人空间链接                    |
| fan_share_image            | str  |                             |                                                     |
| gray_rule                  | str  |                             | **布尔型转换的字符串，作用尚不明确**                |
| gray_rule_type             | str  |                             | **作用尚不明确**                                    |
| image_cover                | str  | 图片封面链接                |                                                     |
| image_cover_color          | str  | 图片封面颜色                |                                                     |
| is_hide                    | str  | 是否隐藏                    | **布尔型转换的字符串，作用尚不明确**                |
| item_id_card               | str  | 动态卡片id                  |                                                     |
| item_id_emoji              | str  | 表情包id                    |                                                     |
| item_id_thumbup            | str  | 动态点赞特效id              |                                                     |
| open_platform_vip_discount | str  | 是否开启平台VIP折扣         |                                                     |
| owner_uid                  | str  | 装扮所有者的用户uid         |                                                     |
| rank_investor_show         | str  | ?显示投资者排名             | **布尔型转换的字符串，作用尚不明确**                |
| realname_auth              | str  |                             | **布尔型转换的字符串，作用尚不明确**                |
| sale_bp_forever_raw        | str  |                             |                                                     |
| sale_bp_pm_raw             | str  |                             |                                                     |
| sale_buy_num_limit         | str  | 促销限制数量                |                                                     |
| sale_quantity              | str  | 促销质量                    | 整数型转换的字符串，"10000"可能表示的是这张图的原画 |
| sale_quantity_limit        | str  | ?是否限制某些质量装扮的销售 | **布尔型转换的字符串，作用尚不明确**                |
| sale_region_ip_limit       | str  | 促销限制地区                |                                                     |
| sale_reserve_switch        | str  |                             | **布尔型转换的字符串，作用尚不明确**                |
| sale_time_begin            | str  | 促销开始时间的时间戳        |                                                     |
| sale_type                  | str  | 促销类型                    |                                                     |
| suit_card_type             | str  | 装扮卡片类型                |                                                     |
| type                       | str  | 类型                        | **作用尚不明确**                                    |

`suit_items` 对象（可能不全，会继续补充）：

| 字段          | 类型  | 内容         | 备注 |
| ------------- | ----- | ------------ | ---- |
| card          | array | 动态卡片     |      |
| emoji_package | array | 表情包       |      |
| card_bg       | array | 专属评论装扮 |      |
| thumbup       | array | 动态点赞特效 |      |
| loading       | array | 专属加载动画 |      |
| play_icon     | array | 专属进度条   |      |
| skin          | array | 专属个性主题 |      |
| space_bg      | array | 专属空间海报 |      |

`suit_items` 中每个数组的对象：

**即上文中所列出的 `suit_items` 中的那些数组对象，对于这些数组，<br />它们其中的字段基本都是相同的，不同的地方会在后面继续说明。**

| 字段             | 类型 | 内容           | 备注                                         |
| ---------------- | ---- | -------------- | -------------------------------------------- |
| item_id          | num  | 装扮id         |                                              |
| name             | str  | 装扮名称       |                                              |
| state            | str  | 状态           |                                              |
| tab_id           | num  | 分栏id         |                                              |
| suit_item_id     | num  | 所属装扮的id   |                                              |
| properties       | obj  | 装扮具体属性   | **不同点主要集中在这个地方，下文将继续说明** |
| current_activity | str  | 当前活动       |                                              |
| next_activity    | obj  | 下一个活动     |                                              |
| current_sources  | str  |                | **作用尚不明确**                             |
| finish_sources   | str  |                | **作用尚不明确**                             |
| sale_left_time   | str  |                | **作用尚不明确**                             |
| sale_time_end    | str  |                | **作用尚不明确**                             |
| sale_surplus     | str  | 商品剩余数量   |                                              |
| items            | str  | 装扮的具体内容 |                                              |

关于上述提到的 `properties` 对象中的共有字段：

| 字段                | 类型 | 内容     | 备注                                 |
| ------------------- | ---- | -------- | ------------------------------------ |
| gray_rule           | str  |          | **布尔型转换的字符串，作用尚不明确** |
| gray_rule_type      | str  |          | **作用尚不明确**                     |
| realname_auth       | str  |          | **布尔型转换的字符串，作用尚不明确** |
| sale_type           | str  | 促销类型 |                                      |
| image               | str  | 图片     |                                      |
| image_preview_small | str  | 预览图   |                                      |

`emoji_package` 数组中的对象中 `properties` 对象中的额外字段：

| 字段                    | 类型 | 内容       | 备注                                 |
| ----------------------- | ---- | ---------- | ------------------------------------ |
| addable                 | str  |            | **布尔型转换的字符串，作用尚不明确** |
| biz                     | str  |            | **作用尚不明确**                     |
| is_symbol               | str  |            | **布尔型转换的字符串，作用尚不明确** |
| permanent               | str  | 是否永久   |                                      |
| preview                 | str  |            | **布尔型转换的字符串，作用尚不明确** |
| recently_used           | str  |            | **布尔型转换的字符串，作用尚不明确** |
| recommend               | str  | 是否推荐   |                                      |
| ref_mid                 | str  |            |                                      |
| removable               | str  | 是否可移除 |                                      |
| setting_pannel_not_show | str  |            | **布尔型转换的字符串，作用尚不明确** |
| size                    | str  | 尺寸       |                                      |
| sortable                | str  | 排序类型   |                                      |

`loading` 数组中的对象中 `properties` 对象中的额外字段：

| 字段              | 类型 | 内容                 | 备注 |
| ----------------- | ---- | -------------------- | ---- |
| loading_frame_url | str  | 进度条动画的其中一帧 |      |
| loading_url       | str  | 进度条动画           |      |

`play_icon` 数组中的对象中 `properties` 对象中的额外字段：

| 字段              | 类型 | 内容                   | 备注 |
| ----------------- | ---- | ---------------------- | ---- |
| drag_left_png     | str  | 进度条向左拖动时的图片 |      |
| drag_right_png    | str  | 进度条向右拖动时的图片 |      |
| middle_png        | str  | 进度条暂停时的图片     |      |
| squared_image     | str  | 效果图                 |      |
| static_icon_image | str  | 静态图标               |      |

`skin` 数组中的对象中 `properties` 对象中的额外字段：

| 字段                          | 类型 | 内容                                 | 备注 |
| ----------------------------- | ---- | ------------------------------------ | ---- |
| head_bg                       | str  | 首页顶部图片                         |      |
| head_myself_mp4_play          | str  | 个人空间顶部视频动画的播放类型       |      |
| head_myself_squared_bg        | str  | 个人空间顶部图片                     |      |
| head_tab_bg                   | str  | 首页顶部标签栏背景图                 |      |
| image_cover                   | str  | 封面图                               |      |
| package_md5                   | str  | 装扮图包的md5值                      |      |
| package_url                   | str  | 装扮图包的压缩包链接                 |      |
| skin_mode                     | str  | 皮肤模式                             |      |
| tail_bg                       | str  | 首页底部图片                         |      |
| tail_color                    | str  | 首页底部颜色                         |      |
| tail_color_selected           | str  | 首页底部被选中时的颜色               |      |
| tail_icon_ani                 | str  | 首页底部是否播放动画                 |      |
| tail_icon_ani_mode            | str  | 首页底部动画的播放类型               |      |
| tail_icon_channel             | str  | 首页底部“动态”按钮图片               |      |
| tail_icon_dynamic             | str  | 首页底部“发布动态”按钮图片           |      |
| tail_icon_main                | str  | 首页底部“首页”按钮图片               |      |
| tail_icon_mode                | str  | 首页底部图标模式                     |      |
| tail_icon_myself              | str  | 首页底部“我的”按钮图片               |      |
| tail_icon_pub_btn_bg          | str  | 首页底部“发布动态”按钮图片           |      |
| tail_icon_selected_channel    | str  | 首页底部“动态”按钮被选中时的图片     |      |
| tail_icon_selected_dynamic    | str  | 首页底部“发布动态”按钮被选中时的图片 |      |
| tail_icon_selected_main       | str  | 首页底部“首页”按钮被选中时的图片     |      |
| tail_icon_selected_myself     | str  | 首页底部“我的”按钮被选中时的图片     |      |
| tail_icon_selected_pub_btn_bg | str  | 首页底部“发布动态”按钮被选中时的图片 |      |
| tail_icon_selected_shop       | str  | 首页底部“会员购”按钮被选中时的图片   |      |
| tail_icon_shop                | str  | 首页底部“会员购”按钮图片             |      |

`space_bg` 数组中的对象中 `properties` 对象中的额外字段：

| 字段             | 类型 | 内容                   | 备注 |
| ---------------- | ---- | ---------------------- | ---- |
| image1_landscape | str  | 第一张空间海报         |      |
| image1_portrait  | str  | 第一张空间海报（纵向） |      |

**如果是第二张图，则是`image2_xxx`，以此类推。**

**示例：**

```shell
curl -G 'https://api.bilibili.com/x/garb/v2/mall/suit/detail' \
     --data-urlencode 'item_id=418043001' \
```

返回数据

```json
{
    "code": 0,
    "message": "0",
    "ttl": 1,
    "data": {
        "item_id": 418043001,
        "name": "满满音符日记",
        "group_id": 47,
        "group_name": "满满音符日记",
        "part_id": 6,
        "state": "active",
        "properties": {
            "desc": "满满的专属个性装扮上线啦！\n软乎乎的少女画风搭配音符、话筒、星光元素，还有小柴陪伴，还原直播间温柔氛围感。\n套装内含专属头像框、动态弹幕、评论点赞动效、全套聊天表情包，搭配满满标志性可爱神态。\n不管是听歌发弹幕、日常评论互动，都能带着小满陪伴，把直播间的温柔与欢喜留在每一条留言里。\n愿你每次点开评论区，都像听见熟悉歌声，岁岁有满音相伴。",
            "fan_id": "418043001",
            "fan_item_ids": "1782712918002,1782713015001,1782713060001,1782713124001,1782713153001,1782713638001",
            "fan_mid": "37754047",
            "fan_share_image": "https://i0.hdslb.com/bfs/garb/51a8338dc627ac5b3e146f95bca05485078de461.png",
            "first_up": "1784368800",
            "gray_rule": "true",
            "gray_rule_type": "all",
            "image_cover": "https://i0.hdslb.com/bfs/garb/ca8017afb6bab54279128a18358efca5ff89f3ae.jpg",
            "image_cover_color": "#B79D8C",
            "item_id_card": "1782712918001",
            "item_id_emoji_package": "1782713678001",
            "item_id_thumbup": "1782713092001",
            "item_stock_surplus": "318676",
            "owner_uid": "438292030",
            "rank_investor_show": "false",
            "sale_bp_forever_raw": "6500",
            "sale_bp_pm_raw": "1000",
            "sale_buy_num_limit": "99",
            "sale_quantity": "319521",
            "sale_quantity_limit": "true",
            "sale_region_ip_limit": "全球",
            "sale_reserve_switch": "true",
            "sale_sku_id_1": "4180430012",
            "sale_sku_id_2": "4180430011",
            "sale_time_begin": "1784455200",
            "sale_type": "pay",
            "suit_card_type": "big_img",
            "type": "ip",
            "user_vas_order": "true"
        },
        "current_activity": null,
        "next_activity": {
            "type": "vip_discount",
            "time_limit": true,
            "time_left": 174042,
            "tag": "大会员限时折扣",
            "price_bp_month": 800,
            "price_bp_forever": 5200,
            "type_month": "vip_discount",
            "tag_month": "大会员限时折扣",
            "time_limit_month": true,
            "time_left_month": 174042
        },
        "current_sources": null,
        "finish_sources": null,
        "sale_left_time": -85158,
        "sale_time_end": -1784540358,
        "sale_surplus": 318676,
        "sale_count_desc": "",
        "total_count_desc": "",
        "tag": "新品",
        "jump_link": "",
        "sales_mode": 0,
        "tracking_info": "",
        "suit_items": {
            "card": [
                {
                    "item_id": 1782712918002,
                    "name": "咻咻满粉丝",
                    "state": "active",
                    "tab_id": 0,
                    "suit_item_id": 418043001,
                    "properties": {
                        "fan_no_color": "#FFD0E9",
                        "fans_image": "https://i0.hdslb.com/bfs/garb/d6ff8f1d8480e1d1ee77ab1e81fbfeec57b23b1e.png",
                        "fans_material_id": "1782712918002",
                        "goods_type": "suit",
                        "hot": "false",
                        "image": "https://i0.hdslb.com/bfs/garb/d6ff8f1d8480e1d1ee77ab1e81fbfeec57b23b1e.png",
                        "image_preview_small": "https://i0.hdslb.com/bfs/garb/c16ed99d6ce791a6b9947b82dbfb501dabe5f198.png",
                        "sale_type": "other"
                    },
                    "current_activity": null,
                    "next_activity": null,
                    "current_sources": null,
                    "finish_sources": null,
                    "sale_left_time": -1784540358,
                    "sale_time_end": -1784540358,
                    "sale_surplus": 0,
                    "items": null
                },
                {
                    "item_id": 1782712918001,
                    "name": "咻咻满",
                    "state": "active",
                    "tab_id": 0,
                    "suit_item_id": 418043001,
                    "properties": {
                        "fan_no_color": "#FFD0E9",
                        "fans_image": "https://i0.hdslb.com/bfs/garb/d6ff8f1d8480e1d1ee77ab1e81fbfeec57b23b1e.png",
                        "fans_material_id": "1782712918002",
                        "goods_type": "suit",
                        "hot": "false",
                        "image": "https://i0.hdslb.com/bfs/garb/9c7d94d46fdb5083cbb372999eb5a2cfb745251c.png",
                        "sale_type": "other"
                    },
                    "current_activity": null,
                    "next_activity": null,
                    "current_sources": null,
                    "finish_sources": null,
                    "sale_left_time": -1784540358,
                    "sale_time_end": -1784540358,
                    "sale_surplus": 0,
                    "items": null
                }
            ],
            "card_bg": [
                {
                    "item_id": 1782713015001,
                    "name": "咻咻满",
                    "state": "active",
                    "tab_id": 0,
                    "suit_item_id": 418043001,
                    "properties": {
                        "fan_no_color": "#E32C2A",
                        "goods_type": "suit",
                        "image": "https://i0.hdslb.com/bfs/baselabs/op/b5fd22b1295f19ba8faef07ba0eb02aa06a1e9bf8492d0054da549d05e72c719.png",
                        "image_preview_small": "https://i0.hdslb.com/bfs/garb/94dc8e072fc114c29a6f2799c433099fbbf0de2f.png",
                        "sale_type": "suit"
                    },
                    "current_activity": null,
                    "next_activity": null,
                    "current_sources": null,
                    "finish_sources": null,
                    "sale_left_time": -1784540358,
                    "sale_time_end": -1784540358,
                    "sale_surplus": 0,
                    "items": null
                }
            ],
            "emoji_package": [
                {
                    "item_id": 1782713678001,
                    "name": "咻咻满",
                    "state": "active",
                    "tab_id": 0,
                    "suit_item_id": 418043001,
                    "properties": {
                        "addable": "true",
                        "biz": "reply,dynamic,watch_full",
                        "goods_type": "suit",
                        "image": "https://i0.hdslb.com/bfs/garb/e4b269ae525dc93ca4c1a7fb40c1671592afc588.png",
                        "is_symbol": "false",
                        "item_emoji_list": "[{\"name\":\"打call\",\"image\":\"https://i0.hdslb.com/bfs/garb/688b31cf7ecbe4de421f4e71c0ec17878f1ac89e.png\"},{\"name\":\"喜欢你\",\"image\":\"https://i0.hdslb.com/bfs/garb/46898da491c0611f537c13d83a404af25449411c.png\"},{\"name\":\"权威\",\"image\":\"https://i0.hdslb.com/bfs/garb/bf459f1040da48429a2b48c110bf8163bf69d152.png\"},{\"name\":\"确实\",\"image\":\"https://i0.hdslb.com/bfs/garb/22acb00759598f76923f51ca549b25f8e2fea512.png\"},{\"name\":\"呜呜\",\"image\":\"https://i0.hdslb.com/bfs/garb/8c7cb2eef345ecf6b4a25bdf71e3ba7ddfa2facc.png\"},{\"name\":\"问号\",\"image\":\"https://i0.hdslb.com/bfs/garb/51ad8bd74ece4236678d6726b0204a8a44980848.png\"},{\"name\":\"感谢老板\",\"image\":\"https://i0.hdslb.com/bfs/garb/715e1c2d2ac3ed9a04b83d788b2beddad915e4e1.png\"},{\"name\":\"冲\",\"image\":\"https://i0.hdslb.com/bfs/garb/01d01c0781fb1cdb72fa6d879e09d51289773600.png\"},{\"name\":\"吓鼠\",\"image\":\"https://i0.hdslb.com/bfs/garb/c51af1e3625e04895ec99b234bf72b365f34b5a6.png\"},{\"name\":\"叹气\",\"image\":\"https://i0.hdslb.com/bfs/garb/6ef1a4dff6fdc26e10db8efcd9806651d3d7b7bf.png\"},{\"name\":\"生气\",\"image\":\"https://i0.hdslb.com/bfs/garb/070ad0019f2bc0c1dbe1a6835a0a153d3d2481b7.png\"},{\"name\":\"晕\",\"image\":\"https://i0.hdslb.com/bfs/garb/5e9a31aac7425b84b6be96de0edba9f4c8e2aeb9.png\"},{\"name\":\"打咩\",\"image\":\"https://i0.hdslb.com/bfs/garb/f8379d3158b18570b127ac68bf5c5d6d571e7355.png\"},{\"name\":\"摸鱼\",\"image\":\"https://i0.hdslb.com/bfs/garb/7a8eeb4ae4a3676ea1822acfe87cef03ec0618ae.png\"},{\"name\":\"晚安\",\"image\":\"https://i0.hdslb.com/bfs/garb/f4eb1f9457e196219dc9e4ff3301ab648a6f61fe.png\"},{\"name\":\"吃枣\",\"image\":\"https://i0.hdslb.com/bfs/garb/5144d7464b80d5d4773b25fe5d8f64f61f54246b.png\"},{\"name\":\"吃瓜\",\"image\":\"https://i0.hdslb.com/bfs/garb/afaa3d3274caab26df9fc331e3155067c1c976cc.png\"},{\"name\":\"资本\",\"image\":\"https://i0.hdslb.com/bfs/garb/53feb1087777949208284e7bef1434d7cfffbd8f.png\"},{\"name\":\"欧气喷雾\",\"image\":\"https://i0.hdslb.com/bfs/garb/e4159a92afd275d9d027be05217a410a73b244b7.png\"},{\"name\":\"趣味生煎\",\"image\":\"https://i0.hdslb.com/bfs/garb/1ee8e7cebfc95f0f86b5fd89d315281088496b6f.png\"},{\"name\":\"啊对对对\",\"image\":\"https://i0.hdslb.com/bfs/garb/8f83c778009cead4c995355b5429b83e5ebd1cc8.png\"},{\"name\":\"给你一拳\",\"image\":\"https://i0.hdslb.com/bfs/garb/7ef428b6cd8c1cd912817c321626beb93807eccb.png\"},{\"name\":\"急\",\"image\":\"https://i0.hdslb.com/bfs/garb/17b506bec1dfd3896b7000d72c37652f6183cb73.png\"},{\"name\":\"咕咕\",\"image\":\"https://i0.hdslb.com/bfs/garb/ee5b6ccb277b98c23d469d63c28c0a7173fa2c69.png\"},{\"name\":\"真正的音乐\",\"image\":\"https://i0.hdslb.com/bfs/garb/38f4b502cba0eb649f3759d5203b724889cab1c2.png\"}]",
                        "permanent": "false",
                        "preview": "false",
                        "recently_used": "false",
                        "recommend": "false",
                        "removable": "true",
                        "resource_type": "0",
                        "sale_type": "pay",
                        "setting_pannel_not_show": "false",
                        "size": "L",
                        "sortable": "true"
                    },
                    "current_activity": null,
                    "next_activity": null,
                    "current_sources": null,
                    "finish_sources": null,
                    "sale_left_time": -1784540358,
                    "sale_time_end": -1784540358,
                    "sale_surplus": 0,
                    "items": [
                        {
                            "item_id": 0,
                            "name": "[咻咻满_打call]",
                            "state": "active",
                            "tab_id": 0,
                            "suit_item_id": 0,
                            "properties": {
                                "image": "https://i0.hdslb.com/bfs/garb/688b31cf7ecbe4de421f4e71c0ec17878f1ac89e.png",
                                "sale_type": "pay"
                            },
                            "current_activity": null,
                            "next_activity": null,
                            "current_sources": null,
                            "finish_sources": null,
                            "sale_left_time": -1784540358,
                            "sale_time_end": -1784540358,
                            "sale_surplus": 0
                        },
                        {
                            "item_id": 0,
                            "name": "[咻咻满_喜欢你]",
                            "state": "active",
                            "tab_id": 0,
                            "suit_item_id": 0,
                            "properties": {
                                "image": "https://i0.hdslb.com/bfs/garb/46898da491c0611f537c13d83a404af25449411c.png",
                                "sale_type": "pay"
                            },
                            "current_activity": null,
                            "next_activity": null,
                            "current_sources": null,
                            "finish_sources": null,
                            "sale_left_time": -1784540358,
                            "sale_time_end": -1784540358,
                            "sale_surplus": 0
                        },
                        {
                            "item_id": 0,
                            "name": "[咻咻满_权威]",
                            "state": "active",
                            "tab_id": 0,
                            "suit_item_id": 0,
                            "properties": {
                                "image": "https://i0.hdslb.com/bfs/garb/bf459f1040da48429a2b48c110bf8163bf69d152.png",
                                "sale_type": "pay"
                            },
                            "current_activity": null,
                            "next_activity": null,
                            "current_sources": null,
                            "finish_sources": null,
                            "sale_left_time": -1784540358,
                            "sale_time_end": -1784540358,
                            "sale_surplus": 0
                        },
                        {
                            "item_id": 0,
                            "name": "[咻咻满_确实]",
                            "state": "active",
                            "tab_id": 0,
                            "suit_item_id": 0,
                            "properties": {
                                "image": "https://i0.hdslb.com/bfs/garb/22acb00759598f76923f51ca549b25f8e2fea512.png",
                                "sale_type": "pay"
                            },
                            "current_activity": null,
                            "next_activity": null,
                            "current_sources": null,
                            "finish_sources": null,
                            "sale_left_time": -1784540358,
                            "sale_time_end": -1784540358,
                            "sale_surplus": 0
                        },
                        {
                            "item_id": 0,
                            "name": "[咻咻满_呜呜]",
                            "state": "active",
                            "tab_id": 0,
                            "suit_item_id": 0,
                            "properties": {
                                "image": "https://i0.hdslb.com/bfs/garb/8c7cb2eef345ecf6b4a25bdf71e3ba7ddfa2facc.png",
                                "sale_type": "pay"
                            },
                            "current_activity": null,
                            "next_activity": null,
                            "current_sources": null,
                            "finish_sources": null,
                            "sale_left_time": -1784540358,
                            "sale_time_end": -1784540358,
                            "sale_surplus": 0
                        },
                        {
                            "item_id": 0,
                            "name": "[咻咻满_问号]",
                            "state": "active",
                            "tab_id": 0,
                            "suit_item_id": 0,
                            "properties": {
                                "image": "https://i0.hdslb.com/bfs/garb/51ad8bd74ece4236678d6726b0204a8a44980848.png",
                                "sale_type": "pay"
                            },
                            "current_activity": null,
                            "next_activity": null,
                            "current_sources": null,
                            "finish_sources": null,
                            "sale_left_time": -1784540358,
                            "sale_time_end": -1784540358,
                            "sale_surplus": 0
                        },
                        {
                            "item_id": 0,
                            "name": "[咻咻满_感谢老板]",
                            "state": "active",
                            "tab_id": 0,
                            "suit_item_id": 0,
                            "properties": {
                                "image": "https://i0.hdslb.com/bfs/garb/715e1c2d2ac3ed9a04b83d788b2beddad915e4e1.png",
                                "sale_type": "pay"
                            },
                            "current_activity": null,
                            "next_activity": null,
                            "current_sources": null,
                            "finish_sources": null,
                            "sale_left_time": -1784540358,
                            "sale_time_end": -1784540358,
                            "sale_surplus": 0
                        },
                        {
                            "item_id": 0,
                            "name": "[咻咻满_冲]",
                            "state": "active",
                            "tab_id": 0,
                            "suit_item_id": 0,
                            "properties": {
                                "image": "https://i0.hdslb.com/bfs/garb/01d01c0781fb1cdb72fa6d879e09d51289773600.png",
                                "sale_type": "pay"
                            },
                            "current_activity": null,
                            "next_activity": null,
                            "current_sources": null,
                            "finish_sources": null,
                            "sale_left_time": -1784540358,
                            "sale_time_end": -1784540358,
                            "sale_surplus": 0
                        },
                        {
                            "item_id": 0,
                            "name": "[咻咻满_吓鼠]",
                            "state": "active",
                            "tab_id": 0,
                            "suit_item_id": 0,
                            "properties": {
                                "image": "https://i0.hdslb.com/bfs/garb/c51af1e3625e04895ec99b234bf72b365f34b5a6.png",
                                "sale_type": "pay"
                            },
                            "current_activity": null,
                            "next_activity": null,
                            "current_sources": null,
                            "finish_sources": null,
                            "sale_left_time": -1784540358,
                            "sale_time_end": -1784540358,
                            "sale_surplus": 0
                        },
                        {
                            "item_id": 0,
                            "name": "[咻咻满_叹气]",
                            "state": "active",
                            "tab_id": 0,
                            "suit_item_id": 0,
                            "properties": {
                                "image": "https://i0.hdslb.com/bfs/garb/6ef1a4dff6fdc26e10db8efcd9806651d3d7b7bf.png",
                                "sale_type": "pay"
                            },
                            "current_activity": null,
                            "next_activity": null,
                            "current_sources": null,
                            "finish_sources": null,
                            "sale_left_time": -1784540358,
                            "sale_time_end": -1784540358,
                            "sale_surplus": 0
                        },
                        {
                            "item_id": 0,
                            "name": "[咻咻满_生气]",
                            "state": "active",
                            "tab_id": 0,
                            "suit_item_id": 0,
                            "properties": {
                                "image": "https://i0.hdslb.com/bfs/garb/070ad0019f2bc0c1dbe1a6835a0a153d3d2481b7.png",
                                "sale_type": "pay"
                            },
                            "current_activity": null,
                            "next_activity": null,
                            "current_sources": null,
                            "finish_sources": null,
                            "sale_left_time": -1784540358,
                            "sale_time_end": -1784540358,
                            "sale_surplus": 0
                        },
                        {
                            "item_id": 0,
                            "name": "[咻咻满_晕]",
                            "state": "active",
                            "tab_id": 0,
                            "suit_item_id": 0,
                            "properties": {
                                "image": "https://i0.hdslb.com/bfs/garb/5e9a31aac7425b84b6be96de0edba9f4c8e2aeb9.png",
                                "sale_type": "pay"
                            },
                            "current_activity": null,
                            "next_activity": null,
                            "current_sources": null,
                            "finish_sources": null,
                            "sale_left_time": -1784540358,
                            "sale_time_end": -1784540358,
                            "sale_surplus": 0
                        },
                        {
                            "item_id": 0,
                            "name": "[咻咻满_打咩]",
                            "state": "active",
                            "tab_id": 0,
                            "suit_item_id": 0,
                            "properties": {
                                "image": "https://i0.hdslb.com/bfs/garb/f8379d3158b18570b127ac68bf5c5d6d571e7355.png",
                                "sale_type": "pay"
                            },
                            "current_activity": null,
                            "next_activity": null,
                            "current_sources": null,
                            "finish_sources": null,
                            "sale_left_time": -1784540358,
                            "sale_time_end": -1784540358,
                            "sale_surplus": 0
                        },
                        {
                            "item_id": 0,
                            "name": "[咻咻满_摸鱼]",
                            "state": "active",
                            "tab_id": 0,
                            "suit_item_id": 0,
                            "properties": {
                                "image": "https://i0.hdslb.com/bfs/garb/7a8eeb4ae4a3676ea1822acfe87cef03ec0618ae.png",
                                "sale_type": "pay"
                            },
                            "current_activity": null,
                            "next_activity": null,
                            "current_sources": null,
                            "finish_sources": null,
                            "sale_left_time": -1784540358,
                            "sale_time_end": -1784540358,
                            "sale_surplus": 0
                        },
                        {
                            "item_id": 0,
                            "name": "[咻咻满_晚安]",
                            "state": "active",
                            "tab_id": 0,
                            "suit_item_id": 0,
                            "properties": {
                                "image": "https://i0.hdslb.com/bfs/garb/f4eb1f9457e196219dc9e4ff3301ab648a6f61fe.png",
                                "sale_type": "pay"
                            },
                            "current_activity": null,
                            "next_activity": null,
                            "current_sources": null,
                            "finish_sources": null,
                            "sale_left_time": -1784540358,
                            "sale_time_end": -1784540358,
                            "sale_surplus": 0
                        },
                        {
                            "item_id": 0,
                            "name": "[咻咻满_吃枣]",
                            "state": "active",
                            "tab_id": 0,
                            "suit_item_id": 0,
                            "properties": {
                                "image": "https://i0.hdslb.com/bfs/garb/5144d7464b80d5d4773b25fe5d8f64f61f54246b.png",
                                "sale_type": "pay"
                            },
                            "current_activity": null,
                            "next_activity": null,
                            "current_sources": null,
                            "finish_sources": null,
                            "sale_left_time": -1784540358,
                            "sale_time_end": -1784540358,
                            "sale_surplus": 0
                        },
                        {
                            "item_id": 0,
                            "name": "[咻咻满_吃瓜]",
                            "state": "active",
                            "tab_id": 0,
                            "suit_item_id": 0,
                            "properties": {
                                "image": "https://i0.hdslb.com/bfs/garb/afaa3d3274caab26df9fc331e3155067c1c976cc.png",
                                "sale_type": "pay"
                            },
                            "current_activity": null,
                            "next_activity": null,
                            "current_sources": null,
                            "finish_sources": null,
                            "sale_left_time": -1784540358,
                            "sale_time_end": -1784540358,
                            "sale_surplus": 0
                        },
                        {
                            "item_id": 0,
                            "name": "[咻咻满_资本]",
                            "state": "active",
                            "tab_id": 0,
                            "suit_item_id": 0,
                            "properties": {
                                "image": "https://i0.hdslb.com/bfs/garb/53feb1087777949208284e7bef1434d7cfffbd8f.png",
                                "sale_type": "pay"
                            },
                            "current_activity": null,
                            "next_activity": null,
                            "current_sources": null,
                            "finish_sources": null,
                            "sale_left_time": -1784540358,
                            "sale_time_end": -1784540358,
                            "sale_surplus": 0
                        },
                        {
                            "item_id": 0,
                            "name": "[咻咻满_欧气喷雾]",
                            "state": "active",
                            "tab_id": 0,
                            "suit_item_id": 0,
                            "properties": {
                                "image": "https://i0.hdslb.com/bfs/garb/e4159a92afd275d9d027be05217a410a73b244b7.png",
                                "sale_type": "pay"
                            },
                            "current_activity": null,
                            "next_activity": null,
                            "current_sources": null,
                            "finish_sources": null,
                            "sale_left_time": -1784540358,
                            "sale_time_end": -1784540358,
                            "sale_surplus": 0
                        },
                        {
                            "item_id": 0,
                            "name": "[咻咻满_趣味生煎]",
                            "state": "active",
                            "tab_id": 0,
                            "suit_item_id": 0,
                            "properties": {
                                "image": "https://i0.hdslb.com/bfs/garb/1ee8e7cebfc95f0f86b5fd89d315281088496b6f.png",
                                "sale_type": "pay"
                            },
                            "current_activity": null,
                            "next_activity": null,
                            "current_sources": null,
                            "finish_sources": null,
                            "sale_left_time": -1784540358,
                            "sale_time_end": -1784540358,
                            "sale_surplus": 0
                        },
                        {
                            "item_id": 0,
                            "name": "[咻咻满_啊对对对]",
                            "state": "active",
                            "tab_id": 0,
                            "suit_item_id": 0,
                            "properties": {
                                "image": "https://i0.hdslb.com/bfs/garb/8f83c778009cead4c995355b5429b83e5ebd1cc8.png",
                                "sale_type": "pay"
                            },
                            "current_activity": null,
                            "next_activity": null,
                            "current_sources": null,
                            "finish_sources": null,
                            "sale_left_time": -1784540358,
                            "sale_time_end": -1784540358,
                            "sale_surplus": 0
                        },
                        {
                            "item_id": 0,
                            "name": "[咻咻满_给你一拳]",
                            "state": "active",
                            "tab_id": 0,
                            "suit_item_id": 0,
                            "properties": {
                                "image": "https://i0.hdslb.com/bfs/garb/7ef428b6cd8c1cd912817c321626beb93807eccb.png",
                                "sale_type": "pay"
                            },
                            "current_activity": null,
                            "next_activity": null,
                            "current_sources": null,
                            "finish_sources": null,
                            "sale_left_time": -1784540358,
                            "sale_time_end": -1784540358,
                            "sale_surplus": 0
                        },
                        {
                            "item_id": 0,
                            "name": "[咻咻满_急]",
                            "state": "active",
                            "tab_id": 0,
                            "suit_item_id": 0,
                            "properties": {
                                "image": "https://i0.hdslb.com/bfs/garb/17b506bec1dfd3896b7000d72c37652f6183cb73.png",
                                "sale_type": "pay"
                            },
                            "current_activity": null,
                            "next_activity": null,
                            "current_sources": null,
                            "finish_sources": null,
                            "sale_left_time": -1784540358,
                            "sale_time_end": -1784540358,
                            "sale_surplus": 0
                        },
                        {
                            "item_id": 0,
                            "name": "[咻咻满_咕咕]",
                            "state": "active",
                            "tab_id": 0,
                            "suit_item_id": 0,
                            "properties": {
                                "image": "https://i0.hdslb.com/bfs/garb/ee5b6ccb277b98c23d469d63c28c0a7173fa2c69.png",
                                "sale_type": "pay"
                            },
                            "current_activity": null,
                            "next_activity": null,
                            "current_sources": null,
                            "finish_sources": null,
                            "sale_left_time": -1784540358,
                            "sale_time_end": -1784540358,
                            "sale_surplus": 0
                        },
                        {
                            "item_id": 0,
                            "name": "[咻咻满_真正的音乐]",
                            "state": "active",
                            "tab_id": 0,
                            "suit_item_id": 0,
                            "properties": {
                                "image": "https://i0.hdslb.com/bfs/garb/38f4b502cba0eb649f3759d5203b724889cab1c2.png",
                                "sale_type": "pay"
                            },
                            "current_activity": null,
                            "next_activity": null,
                            "current_sources": null,
                            "finish_sources": null,
                            "sale_left_time": -1784540358,
                            "sale_time_end": -1784540358,
                            "sale_surplus": 0
                        }
                    ]
                }
            ],
            "loading": [
                {
                    "item_id": 1782713124001,
                    "name": "咻咻满",
                    "state": "active",
                    "tab_id": 0,
                    "suit_item_id": 418043001,
                    "properties": {
                        "goods_type": "suit",
                        "image_preview_small": "https://i0.hdslb.com/bfs/garb/9b10dd24d66428496ce59929b8c6d76e84475661.png",
                        "loading_frame_url": "https://i0.hdslb.com/bfs/baselabs/op/c1fe76b81694894e0bcb552bfccef15df44a89ab0701f0007ea49dabc908289b.png",
                        "loading_url": "https://i0.hdslb.com/bfs/baselabs/op/97078750fe9d8a1758c6754ee4ce16bc68ca29a1766ede0a2a806681aa59beba.webp",
                        "ver": "1784368500"
                    },
                    "current_activity": null,
                    "next_activity": null,
                    "current_sources": null,
                    "finish_sources": null,
                    "sale_left_time": -1784540358,
                    "sale_time_end": -1784540358,
                    "sale_surplus": 0,
                    "items": null
                }
            ],
            "play_icon": [
                {
                    "item_id": 1782713153001,
                    "name": "咻咻满",
                    "state": "active",
                    "tab_id": 0,
                    "suit_item_id": 418043001,
                    "properties": {
                        "drag_left_png": "https://i0.hdslb.com/bfs/garb/842de968518191b63c7a8f95ef043c889bbf707a.png",
                        "drag_right_png": "https://i0.hdslb.com/bfs/garb/0250131b1e9a563842df91663cb83c1dcf34f95f.png",
                        "goods_type": "suit",
                        "middle_png": "https://i0.hdslb.com/bfs/garb/8b1e13aef90b91933ee194892a44e9ea35ad078b.png",
                        "squared_image": "https://i0.hdslb.com/bfs/baselabs/op/66a14b3c6299976dadcf52596968f78006cdf057cd26a10b3a3e5835834d71f3.png",
                        "static_icon_image": "https://i0.hdslb.com/bfs/garb/3a4b34f08dfa6fa51b5baeb9b1496a9333338569.png",
                        "ver": "1784368500"
                    },
                    "current_activity": null,
                    "next_activity": null,
                    "current_sources": null,
                    "finish_sources": null,
                    "sale_left_time": -1784540358,
                    "sale_time_end": -1784540358,
                    "sale_surplus": 0,
                    "items": null
                }
            ],
            "skin": [
                {
                    "item_id": 1782713638001,
                    "name": "咻咻满",
                    "state": "active",
                    "tab_id": 0,
                    "suit_item_id": 418043001,
                    "properties": {
                        "color": "#ffffff",
                        "color_mode": "dark",
                        "color_second_page": "#1A3475",
                        "goods_type": "suit",
                        "head_bg": "https://i0.hdslb.com/bfs/garb/a6d62083572fc1cf01a78879d5649a73dfd89eb4.png",
                        "head_myself_mp4_bg": "https://upos-sz-mirrorali.bilivideo.com/panguxcodeboss/4b/61/_0000129ntzygw48b92bcfbtfcdw614b-1-162210110000.mp4?e=ig8euxZM2rNcNbdlhoNvNC8BqJIzNbfq9rVEuxTEnE8L5F6VnEsSTx0vkX8fqJeYTj_lta53NCM=&uipk=5&nbs=1&deadline=1784547558&gen=playurlv2&os=alibv&oi=2096107113&trid=3e0e9779f74a46d1b5200a3e834a4c7fB&mid=0&platform=html5&og=ali&upsig=a03b3dc39e8743f962e15be7ce2fc973&uparams=e,uipk,nbs,deadline,gen,os,oi,trid,mid,platform,og&bvc=vod&nettype=0&orderid=0,3&logo=00000000&f=B_0_0",
                        "head_myself_mp4_bg_list": "[\"https://upos-sz-mirrorali.bilivideo.com/panguxcodeboss/4b/61/_0000129ntzygw48b92bcfbtfcdw614b-1-162210110000.mp4?e=ig8euxZM2rNcNbdlhoNvNC8BqJIzNbfq9rVEuxTEnE8L5F6VnEsSTx0vkX8fqJeYTj_lta53NCM=\&uipk=5\&nbs=1\&deadline=1784547558\&gen=playurlv2\&os=alibv\&oi=2096107113\&trid=3e0e9779f74a46d1b5200a3e834a4c7fB\&mid=0\&platform=html5\&og=ali\&upsig=a03b3dc39e8743f962e15be7ce2fc973\&uparams=e,uipk,nbs,deadline,gen,os,oi,trid,mid,platform,og\&bvc=vod\&nettype=0\&orderid=0,3\&logo=00000000\&f=B_0_0\",\"https://upos-sz-estgoss.bilivideo.com/panguxcodeboss/4b/61/_0000129ntzygw48b92bcfbtfcdw614b-1-162210110000.mp4?e=ig8euxZM2rNcNbdlhoNvNC8BqJIzNbfq9rVEuxTEnE8L5F6VnEsSTx0vkX8fqJeYTj_lta53NCM=\&uipk=5\&nbs=1\&deadline=1784547558\&gen=playurlv2\&os=upos\&oi=2096107113\&trid=3e0e9779f74a46d1b5200a3e834a4c7fB\&mid=0\&platform=html5\&og=ali\&upsig=c200abc042fcb430454fbd95f5368cf1\&uparams=e,uipk,nbs,deadline,gen,os,oi,trid,mid,platform,og\&bvc=vod\&nettype=0\&orderid=1,3\&logo=00000000\&f=B_0_0\",\"https://upos-sz-mirrorali.bilivideo.com/panguxcodeboss/4b/61/_0000129ntzygw48b92bcfbtfcdw614b-1-162210110000.mp4?e=ig8euxZM2rNcNbdlhoNvNC8BqJIzNbfq9rVEuxTEnE8L5F6VnEsSTx0vkX8fqJeYTj_lta53NCM=\&uipk=5\&nbs=1\&deadline=1784547558\&gen=playurlv2\&os=alibv\&oi=2096107113\&trid=3e0e9779f74a46d1b5200a3e834a4c7fB\&mid=0\&platform=html5\&og=ali\&upsig=a03b3dc39e8743f962e15be7ce2fc973\&uparams=e,uipk,nbs,deadline,gen,os,oi,trid,mid,platform,og\&bvc=vod\&nettype=0\&orderid=2,3\&logo=00000000\&f=B_0_0\"]",
                        "head_myself_mp4_play": "loop",
                        "head_myself_squared_bg": "",
                        "head_tab_bg": "https://i0.hdslb.com/bfs/baselabs/op/d8b29e35765d931135db554932124f25787b5ba17aa6bc7a027ee029309794aa.png",
                        "image_cover": "https://i0.hdslb.com/bfs/garb/ca8017afb6bab54279128a18358efca5ff89f3ae.jpg",
                        "image_preview": "https://i0.hdslb.com/bfs/garb/ca8017afb6bab54279128a18358efca5ff89f3ae.jpg",
                        "package_md5": "ed3d5c4a37a0395cffdbfdde11716a0a",
                        "package_url": "https://i0.hdslb.com/bfs/garb/zip/81f37683064dbf0ac50911c061e2711e1508b735.zip",
                        "tail_bg": "https://i0.hdslb.com/bfs/garb/c4b69851f8d4c9d57e22fa35cd9dc4bab244ad6d.png",
                        "tail_color": "#FFFFFF",
                        "tail_color_selected": "#A0B4E0",
                        "tail_icon_channel": "https://i0.hdslb.com/bfs/garb/94ee6eea6dc9b9ef307099efcb5caded5608afae.png",
                        "tail_icon_dynamic": "https://i0.hdslb.com/bfs/garb/94ee6eea6dc9b9ef307099efcb5caded5608afae.png",
                        "tail_icon_main": "https://i0.hdslb.com/bfs/garb/dedae8521ff5f2140d89e6a4475e2e7e5b7439ca.png",
                        "tail_icon_mode": "img",
                        "tail_icon_myself": "https://i0.hdslb.com/bfs/garb/350856a0fdd4e7464da49571142c5d9330892178.png",
                        "tail_icon_pub_btn_bg": "https://i0.hdslb.com/bfs/garb/9cd0ab0f63e69d43cd7777de395f7e3662ee1813.png",
                        "tail_icon_selected_channel": "https://i0.hdslb.com/bfs/garb/5a4bd5e62f2ac6eeffd18e73503bdbbadb755d8f.png",
                        "tail_icon_selected_dynamic": "https://i0.hdslb.com/bfs/garb/5a4bd5e62f2ac6eeffd18e73503bdbbadb755d8f.png",
                        "tail_icon_selected_main": "https://i0.hdslb.com/bfs/garb/5a4bd5e62f2ac6eeffd18e73503bdbbadb755d8f.png",
                        "tail_icon_selected_myself": "https://i0.hdslb.com/bfs/garb/5a4bd5e62f2ac6eeffd18e73503bdbbadb755d8f.png",
                        "tail_icon_selected_pub_btn_bg": "https://i0.hdslb.com/bfs/garb/9cd0ab0f63e69d43cd7777de395f7e3662ee1813.png",
                        "tail_icon_selected_shop": "https://i0.hdslb.com/bfs/garb/5a4bd5e62f2ac6eeffd18e73503bdbbadb755d8f.png",
                        "tail_icon_shop": "https://i0.hdslb.com/bfs/garb/d8d1fa817f96453c9ca0e25245673515096c1d9b.png",
                        "ver": "1782777948"
                    },
                    "current_activity": null,
                    "next_activity": null,
                    "current_sources": null,
                    "finish_sources": null,
                    "sale_left_time": -1784540358,
                    "sale_time_end": -1784540358,
                    "sale_surplus": 0,
                    "items": null
                }
            ],
            "space_bg": [
                {
                    "item_id": 1782713060001,
                    "name": "咻咻满",
                    "state": "active",
                    "tab_id": 0,
                    "suit_item_id": 418043001,
                    "properties": {
                        "fan_no_color": "#ffffff",
                        "goods_type": "suit",
                        "image1_landscape": "https://i0.hdslb.com/bfs/garb/4b6224a0a941ebda1a59e596fe82922cddae5b2b.jpg",
                        "image1_portrait": "https://i0.hdslb.com/bfs/garb/item/541ea4669e584860bb6e735f64a6c95d2787ac54.jpg",
                        "image2_landscape": "https://i0.hdslb.com/bfs/garb/72d6a06bbba4098d128f2bf04cdb719577d4768d.jpg",
                        "image2_portrait": "https://i0.hdslb.com/bfs/garb/466cd6f190000d9bd074c8dc45b8532620f49d75.jpg",
                        "image3_landscape": "https://i0.hdslb.com/bfs/garb/47bd1321347dab28385d6f98cf41a2d6c1b2dee4.jpg",
                        "image3_portrait": "https://i0.hdslb.com/bfs/garb/fd93839802e8954efd011dee5930a443f5c701aa.jpg",
                        "image4_landscape": "https://i0.hdslb.com/bfs/garb/08c9e8d2fa474789116d40355f7ca7200c6d65df.jpg",
                        "image4_portrait": "https://i0.hdslb.com/bfs/garb/79c4d9548ce25559eec819243ab60d156b12f333.jpg",
                        "image5_landscape": "https://i0.hdslb.com/bfs/garb/1c6aeaf99f2cbf6a9302f2f16c531a4c774886dc.jpg",
                        "image5_portrait": "https://i0.hdslb.com/bfs/garb/90d05ffa2c3b412f23582b51063af65810b60df3.jpg",
                        "image6_landscape": "https://i0.hdslb.com/bfs/garb/c345da35f6eda89cb85f456d30ca11617465164d.jpg",
                        "image6_portrait": "https://i0.hdslb.com/bfs/garb/c19e375b9c8265d1d9f8332418b3d0b47d904e58.jpg",
                        "image7_landscape": "https://i0.hdslb.com/bfs/garb/f777e9da182de8bdd57dd52f108a03a6ab5353d2.jpg",
                        "image7_portrait": "https://i0.hdslb.com/bfs/garb/5945b3b8b62a9bbd31215c0702e198b29be829b9.jpg",
                        "image8_landscape": "https://i0.hdslb.com/bfs/garb/8da59bf78ef29bb51b6b57a8fad6b59c105b76f7.jpg",
                        "image8_portrait": "https://i0.hdslb.com/bfs/garb/d668beb1852d66a4c6f7d658a39cdfbcf0f71538.jpg",
                        "space_1_mp4_horizontal": "",
                        "space_1_mp4_vertical": "",
                        "space_2_mp4_horizontal": "",
                        "space_2_mp4_vertical": "",
                        "space_3_mp4_horizontal": "",
                        "space_3_mp4_vertical": "",
                        "space_4_mp4_horizontal": "",
                        "space_4_mp4_vertical": "",
                        "space_5_mp4_horizontal": "",
                        "space_5_mp4_vertical": "",
                        "space_6_mp4_horizontal": "",
                        "space_6_mp4_vertical": "",
                        "space_7_mp4_horizontal": "",
                        "space_7_mp4_vertical": "",
                        "space_8_mp4_horizontal": "",
                        "space_8_mp4_vertical": ""
                    },
                    "current_activity": null,
                    "next_activity": null,
                    "current_sources": null,
                    "finish_sources": null,
                    "sale_left_time": -1784540358,
                    "sale_time_end": -1784540358,
                    "sale_surplus": 0,
                    "items": null
                }
            ],
            "thumbup": [
                {
                    "item_id": 1782713092001,
                    "name": "咻咻满",
                    "state": "active",
                    "tab_id": 0,
                    "suit_item_id": 418043001,
                    "properties": {
                        "goods_type": "suit",
                        "image_ani": "https://i0.hdslb.com/bfs/garb/6c1f94dbfaea50bda076b44d2d23a29ddf4b1eab.bin",
                        "image_ani_cut": "https://i0.hdslb.com/bfs/garb/6c1f94dbfaea50bda076b44d2d23a29ddf4b1eab.bin",
                        "image_preview": "https://i0.hdslb.com/bfs/garb/5507f21475bf1ed5d748293ac2253d2be84db324.png"
                    },
                    "current_activity": null,
                    "next_activity": null,
                    "current_sources": null,
                    "finish_sources": null,
                    "sale_left_time": -1784540358,
                    "sale_time_end": -1784540358,
                    "sale_surplus": 0,
                    "items": null
                }
            ]
        },
        "fan_user": {
            "mid": 37754047,
            "nickname": "咻咻满",
            "avatar": "https://i1.hdslb.com/bfs/face/a75d6e7ae0248e4b0f78518dd1e10744580791bb.jpg"
        },
        "unlock_items": null,
        "activity_entrance": {
            "id": 0,
            "item_id": 0,
            "title": "",
            "image_cover": "",
            "jump_link": ""
        }
    }
}
```
