## 装扮/收藏集搜索API

> https://api.bilibili.com/x/garb/v2/mall/home/search

*请求方式: GET*

**URL参数:**

| 参数名 | 类型 | 内容 | 必要性 | 备注 |
|----- |--- |------- |----- |--- |
| key_word | str | 关键词 | 不必要 |  |
| ps | int | 每页返回数据的最大值 | 不必要 | |
| pn | int | 当前页数 | 不必要 | |

**JSON回复:**

根对象:

| 字段 | 类型 | 内容 | 备注 |
|-- |-- |-- |-- |
| code | num | 返回值 | 0：成功 |
| message | str | 错误信息 | 默认为0 |
| ttl | num | 1 |  |
| data | obj | 返回数据 |  |

`data` 对象:

| 字段 | 类型 | 内容 | 备注 |
|-|---|--|--|
| list | array | 返回数据 | 若无则为 null |
| ps | int | 每页返回数据的最大值 | 默认为20 |
| pn | int | 当前页数 | 默认为1 |
| total | int | 查询到数据的总个数 |  |

`data` 中的 `list` 数组中的对象:

| 字段 | 类型 | 内容 | 备注 |
|-|---|--|--|
| item_id | int | 装扮对应的id | 收藏集均为0,需要在properties获取 |
| name | str | 装扮/收藏集名称 | |
| group_id | int | ?分类的id | |
| group_name | str | ?分类的名称 | |
| part_id | int | 类型id | 装扮为6 收藏集为0 |
| state | str | 当前状态 | 默认为“active” |
| properties | obj | 见下方 | |
| current_activity | obj | 见下方 | |
| next_activity | int | ?下次活动的时间 | |
| current_sources | int | ?活动开始时间 | |
| finish_sources | int | ?活动结束时间 | |
| sale_left_time | int | ?销售剩余时间 | |
| sale_time_end | int | ?销售结束时间 | |
| sale_surplus | int | 未知 | |
| sale_count_desc | str | 销售量显示文本 | |
| total_count_desc | str | 总量显示文本 | |
| tag | str | 当前状态标签 | |
| jump_link | str | 跳转链接 | |
| sales_mode | int | ?销售状态 | |

`list` 数组中的对象中的 `properties` 对象:

共有字段:

| 字段 | 类型 | 内容 | 备注|
|-|---|--|--|
| image_cover | str | 图片封面 | |
| sale_bp_forever_raw | str | 价格 | 以0.01B币为单位|
| type | str | 类型 | 收藏集为dlc_act, 装扮为ip|

装扮特有：

| 字段 | 类型 | 内容 | 备注|
| - | - | ---- | ----- |
| desc | str | 介绍文本 | 仅装扮|
| fan_desc | str | 装扮名称 | 仅装扮|
| fan_item_ids | str | 未知 | 仅装扮|
| fan_mid | str | 该up的uid | 仅装扮|
| fan_no_color | str | 十六进制颜色 | 仅装扮|
| fan_recommend_desc | str | 装备说明 | 仅装扮|
| fan_recommend_jump_type | str | 跳转类型 | 仅装扮|
| fan_recommend_jump_value | str | 跳转值 | 仅装扮|
| fan_share_image | str | 分享时的背景图 | 仅装扮|
| gray_rule | str | 未知 | 仅装扮|
| gray_rule_type | str | 未知 | 仅装扮|
| image_cover_color | str | ?图片封面纯色背景 | 仅装扮|
| is_hide | str | 是否隐藏 | 仅装扮|
| item_id_card | str | 装扮背景卡片id | 仅装扮|
| item_id_emoji | str | 装扮表情包id | 仅装扮|
| item_id_thumbup | str | 装扮点赞动画id | 仅装扮|
| open_platform_vip_discount | str | 是否有大会员减免 | 仅装扮|
| owner_uid | str | UID | 默认为虚拟主播衍生品小货架, 仅装扮|
| rank_investor_show | str | 未知 | 仅装扮|
| realname_auth | str | ?是否需要实名认证 | 仅装扮|
| sale_bp_pm_raw | str | 该装扮基础套餐价格 | 以0.01B币为单位, 仅装扮|
| sale_buy_num_limit | str | 购买限额 | 仅装扮|
| sale_quantity | str | 该装扮粉丝专属套餐限额 | 仅装扮|
| sale_quantity_limit | str | 该装扮粉丝专属套餐是否限额 | 仅装扮|
| sale_region_ip_limit | str | 该装扮限制购买地区 | 仅装扮|
| sale_reserve_switch | str | 未知 | 仅装扮|
| sale_time_begin | str | 开始售卖时的时间戳 | 仅装扮|
| sale_type | str | 售卖类型 | 默认为pay, 仅装扮|
| suit_card_type | str | 仅装扮 | |

收藏集特有:

| 字段 | 类型 | 内容 | 备注 |
| - | ---- | - | --------- |
| book_amount | str | 购买总数 | 仅收藏集 |
| dlc_act_id | str | 收藏集活动id | 仅收藏集 |
| dlc_act_status | str | 收藏集活动状态 | 仅收藏集 |
| dlc_is_free | str | 收藏集抽奖是否免费 | 仅收藏集 |
| dlc_lottery_id | str | 收藏集抽奖id | 仅收藏集 |
| dlc_lottery_sale_quantity | str | 购买总数 | 仅收藏集 |
| dlc_lottery_type | str | ?抽奖类型 | 仅收藏集 |
| dlc_sale_end_time | str | 收藏集抽奖结束时间 | 仅收藏集 |
| dlc_sale_mode | str | 未知 | 仅收藏集 |
| dlc_sale_start_time | str | 收藏集抽奖开始时间 | 仅收藏集 |
| dlc_surplus_stock | str | 未知 | 仅收藏集 |

`list` 数组中的对象中的 `current_activity` 对象:

| 字段 | 类型 | 内容 | 备注 |
| - | --- | --- | - |
| type | str | 当前永久价格活动类型 | 装扮一般是open_platform_vip_discount, 收藏集一般是first_draw_discount |
| time_limit | bool | 是否存在时间限制 |  |
| time_left | int | 剩余时间 |  |
| tag | str | 显示标签 |  |
| price_bp_forever | int | 永久价格 | 以0.01B币为单位 |
| price_bp_month | int | 一个月的价格 | 以0.01B币为单位 |
| type_month | str | 当前一个月的价格活动类型 | 仅装扮 |
| tag_month | str | 显示标签 | 仅装扮 |
| time_limit_month | bool | 是否存在时间限制 | 仅装扮 |
| time_left_month | int | 剩余时间 | 仅装扮 |

**示例:**

搜索关键词为 `2233`:

```shell
curl -G 'https://api.bilibili.com/x/garb/v2/mall/home/search' \
--data-urlencode 'key_word=初音未来' 
```

返回数据


```json
{
    "code": 0,
    "message": "0",
    "ttl": 1,
    "data": {
        "list": [
            {
                "item_id": 111106,
                "name": "初音未来live集-未来有你魔法星夜",
                "group_id": 47,
                "group_name": "初音未来live集-未来有你魔法星夜",
                "part_id": 0,
                "state": "active",
                "properties": {
                    "book_amount": "79843",
                    "dlc_act_id": "111106",
                    "dlc_act_status": "2",
                    "dlc_is_free": "0",
                    "dlc_lottery_id": "111107",
                    "dlc_lottery_sale_quantity": "49293",
                    "dlc_lottery_type": "1",
                    "dlc_sale_end_time": "2114406245",
                    "dlc_sale_mode": "1",
                    "dlc_sale_start_time": "1766289600",
                    "dlc_surplus_stock": "0",
                    "image_cover": "https://i0.hdslb.com/bfs/garb/8661422acef10f6c22f247dba9120ce9c702c2c3.jpg",
                    "sale_bp_forever_raw": "990",
                    "type": "dlc_act"
                },
                "current_activity": null,
                "next_activity": null,
                "current_sources": null,
                "finish_sources": null,
                "sale_left_time": -1784539463,
                "sale_time_end": -1784539463,
                "sale_surplus": 0,
                "sale_count_desc": "4万+",
                "total_count_desc": "已售4万+份",
                "tag": "",
                "jump_link": "https://www.bilibili.com/h5/mall/digital-card/home?-Abrowser=live&act_id=111106&hybrid_set_header=2&lottery_id=111107",
                "sales_mode": 0,
                "tracking_info": ""
            },
            {
                "item_id": 109857,
                "name": "初音未来：缤纷舞台-缤纷舞台",
                "group_id": 49,
                "group_name": "初音未来：缤纷舞台-缤纷舞台",
                "part_id": 0,
                "state": "active",
                "properties": {
                    "book_amount": "98160",
                    "dlc_act_id": "109857",
                    "dlc_act_status": "2",
                    "dlc_is_free": "0",
                    "dlc_lottery_id": "109858",
                    "dlc_lottery_sale_quantity": "89910",
                    "dlc_lottery_type": "1",
                    "dlc_sale_end_time": "2114406245",
                    "dlc_sale_mode": "1",
                    "dlc_sale_start_time": "1758945600",
                    "dlc_surplus_stock": "0",
                    "image_cover": "https://i0.hdslb.com/bfs/garb/679adc9353284bd7bdf7432bd87e7d46e282f12e.png",
                    "sale_bp_forever_raw": "990",
                    "type": "dlc_act"
                },
                "current_activity": null,
                "next_activity": null,
                "current_sources": null,
                "finish_sources": null,
                "sale_left_time": -1784539463,
                "sale_time_end": -1784539463,
                "sale_surplus": 0,
                "sale_count_desc": "8万+",
                "total_count_desc": "已售8万+份",
                "tag": "",
                "jump_link": "https://www.bilibili.com/h5/mall/digital-card/home?-Abrowser=live&act_id=109857&hybrid_set_header=2&lottery_id=109858",
                "sales_mode": 0,
                "tracking_info": ""
            },
            {
                "item_id": 109320,
                "name": "初音未来·生日集-Heartbeat",
                "group_id": 47,
                "group_name": "初音未来·生日集-Heartbeat",
                "part_id": 0,
                "state": "active",
                "properties": {
                    "book_amount": "348596",
                    "dlc_act_id": "109320",
                    "dlc_act_status": "2",
                    "dlc_is_free": "0",
                    "dlc_lottery_id": "112875",
                    "dlc_lottery_sale_quantity": "83976",
                    "dlc_lottery_type": "2",
                    "dlc_sale_end_time": "2114406245",
                    "dlc_sale_mode": "1",
                    "dlc_sale_start_time": "1779336000",
                    "dlc_surplus_stock": "1054",
                    "image_cover": "https://i0.hdslb.com/bfs/garb/abf76f07fcd48bff0a8a7457eb81451b45a28660.jpg",
                    "sale_bp_forever_raw": "990",
                    "type": "dlc_act"
                },
                "current_activity": null,
                "next_activity": null,
                "current_sources": null,
                "finish_sources": null,
                "sale_left_time": -1784539463,
                "sale_time_end": -1784539463,
                "sale_surplus": 0,
                "sale_count_desc": "8万+",
                "total_count_desc": "已售8万+份",
                "tag": "DLC池",
                "jump_link": "https://www.bilibili.com/h5/mall/digital-card/home?-Abrowser=live&act_id=109320&hybrid_set_header=2&lottery_id=112875",
                "sales_mode": 0,
                "tracking_info": ""
            },
            {
                "item_id": 111106,
                "name": "初音未来live集-未来有你福利卡池",
                "group_id": 47,
                "group_name": "初音未来live集-未来有你福利卡池",
                "part_id": 0,
                "state": "active",
                "properties": {
                    "book_amount": "79843",
                    "dlc_act_id": "111106",
                    "dlc_act_status": "2",
                    "dlc_is_free": "1",
                    "dlc_lottery_id": "111111",
                    "dlc_lottery_sale_quantity": "30550",
                    "dlc_lottery_type": "2",
                    "dlc_sale_end_time": "2114406245",
                    "dlc_sale_mode": "1",
                    "dlc_sale_start_time": "1766289600",
                    "dlc_surplus_stock": "0",
                    "image_cover": "https://i0.hdslb.com/bfs/garb/8661422acef10f6c22f247dba9120ce9c702c2c3.jpg",
                    "sale_bp_forever_raw": "0",
                    "type": "dlc_act"
                },
                "current_activity": null,
                "next_activity": null,
                "current_sources": null,
                "finish_sources": null,
                "sale_left_time": -1784539463,
                "sale_time_end": -1784539463,
                "sale_surplus": 0,
                "sale_count_desc": "3万+",
                "total_count_desc": "已发放3万+份",
                "tag": "DLC池",
                "jump_link": "https://www.bilibili.com/h5/mall/digital-card/home?-Abrowser=live&act_id=111106&hybrid_set_header=2&lottery_id=111111",
                "sales_mode": 0,
                "tracking_info": ""
            },
            {
                "item_id": 109320,
                "name": "初音未来·生日集-星幕回响",
                "group_id": 47,
                "group_name": "初音未来·生日集-星幕回响",
                "part_id": 0,
                "state": "active",
                "properties": {
                    "book_amount": "348596",
                    "dlc_act_id": "109320",
                    "dlc_act_status": "2",
                    "dlc_is_free": "0",
                    "dlc_lottery_id": "109321",
                    "dlc_lottery_sale_quantity": "264620",
                    "dlc_lottery_type": "1",
                    "dlc_sale_end_time": "2114406245",
                    "dlc_sale_mode": "1",
                    "dlc_sale_start_time": "1756526400",
                    "dlc_surplus_stock": "1054",
                    "image_cover": "https://i0.hdslb.com/bfs/garb/ec5a5b6de41031aa691969e581cdc17ceed3a299.jpg",
                    "sale_bp_forever_raw": "990",
                    "type": "dlc_act"
                },
                "current_activity": null,
                "next_activity": null,
                "current_sources": null,
                "finish_sources": null,
                "sale_left_time": -1784539463,
                "sale_time_end": -1784539463,
                "sale_surplus": 0,
                "sale_count_desc": "20万+",
                "total_count_desc": "已售20万+份",
                "tag": "",
                "jump_link": "https://www.bilibili.com/h5/mall/digital-card/home?-Abrowser=live&act_id=109320&hybrid_set_header=2&lottery_id=109321",
                "sales_mode": 0,
                "tracking_info": ""
            },
            {
                "item_id": 100002,
                "name": "初音未来收藏集-16岁生贺",
                "group_id": 47,
                "group_name": "初音未来收藏集-16岁生贺",
                "part_id": 0,
                "state": "active",
                "properties": {
                    "book_amount": "352518",
                    "dlc_act_id": "100002",
                    "dlc_act_status": "2",
                    "dlc_is_free": "0",
                    "dlc_lottery_id": "100007",
                    "dlc_lottery_sale_quantity": "87679",
                    "dlc_lottery_type": "1",
                    "dlc_sale_end_time": "2114406245",
                    "dlc_sale_mode": "1",
                    "dlc_sale_start_time": "1695189600",
                    "dlc_surplus_stock": "0",
                    "image_cover": "http://i0.hdslb.com/bfs/archive/35624b88a1a9a344aacc699bbcf773f3b07c92db.jpg",
                    "sale_bp_forever_raw": "990",
                    "type": "dlc_act"
                },
                "current_activity": null,
                "next_activity": null,
                "current_sources": null,
                "finish_sources": null,
                "sale_left_time": -1784539463,
                "sale_time_end": -1784539463,
                "sale_surplus": 0,
                "sale_count_desc": "8万+",
                "total_count_desc": "已售8万+份",
                "tag": "",
                "jump_link": "https://www.bilibili.com/h5/mall/digital-card/home?-Abrowser=live&act_id=100002&hybrid_set_header=2&lottery_id=100007",
                "sales_mode": 0,
                "tracking_info": ""
            },
            {
                "item_id": 101116,
                "name": "初音未来单人集-三连快乐",
                "group_id": 47,
                "group_name": "初音未来单人集-三连快乐",
                "part_id": 0,
                "state": "active",
                "properties": {
                    "book_amount": "956508",
                    "dlc_act_id": "101116",
                    "dlc_act_status": "2",
                    "dlc_is_free": "0",
                    "dlc_lottery_id": "101117",
                    "dlc_lottery_sale_quantity": "653562",
                    "dlc_lottery_type": "1",
                    "dlc_sale_end_time": "2114406245",
                    "dlc_sale_mode": "1",
                    "dlc_sale_start_time": "1707883200",
                    "dlc_surplus_stock": "0",
                    "image_cover": "https://i0.hdslb.com/bfs/garb/f55cabcd358421691386d26797cf5c74c988c69f.jpg",
                    "sale_bp_forever_raw": "990",
                    "type": "dlc_act"
                },
                "current_activity": null,
                "next_activity": null,
                "current_sources": null,
                "finish_sources": null,
                "sale_left_time": -1784539463,
                "sale_time_end": -1784539463,
                "sale_surplus": 0,
                "sale_count_desc": "60万+",
                "total_count_desc": "已售60万+份",
                "tag": "",
                "jump_link": "https://www.bilibili.com/h5/mall/digital-card/home?-Abrowser=live&act_id=101116&hybrid_set_header=2&lottery_id=101117",
                "sales_mode": 0,
                "tracking_info": ""
            },
            {
                "item_id": 112266,
                "name": "电影世界计划初音未来-电影世界计划",
                "group_id": 57,
                "group_name": "电影世界计划初音未来-电影世界计划",
                "part_id": 0,
                "state": "active",
                "properties": {
                    "book_amount": "59433",
                    "dlc_act_id": "112266",
                    "dlc_act_status": "2",
                    "dlc_is_free": "0",
                    "dlc_lottery_id": "112267",
                    "dlc_lottery_sale_quantity": "59433",
                    "dlc_lottery_type": "1",
                    "dlc_sale_end_time": "2114406245",
                    "dlc_sale_mode": "1",
                    "dlc_sale_start_time": "1773982800",
                    "dlc_surplus_stock": "0",
                    "image_cover": "https://i0.hdslb.com/bfs/garb/d95954d721802dce87e5169aad2b2d0e54a8db73.jpg",
                    "sale_bp_forever_raw": "990",
                    "type": "dlc_act"
                },
                "current_activity": null,
                "next_activity": null,
                "current_sources": null,
                "finish_sources": null,
                "sale_left_time": -1784539463,
                "sale_time_end": -1784539463,
                "sale_surplus": 0,
                "sale_count_desc": "5万+",
                "total_count_desc": "已售5万+份",
                "tag": "",
                "jump_link": "https://www.bilibili.com/h5/mall/digital-card/home?-Abrowser=live&act_id=112266&hybrid_set_header=2&lottery_id=112267",
                "sales_mode": 0,
                "tracking_info": ""
            },
            {
                "item_id": 112997,
                "name": "初音未来：缤纷舞台第二弹-虚拟歌手组合",
                "group_id": 47,
                "group_name": "初音未来：缤纷舞台第二弹-虚拟歌手组合",
                "part_id": 0,
                "state": "active",
                "properties": {
                    "book_amount": "17786",
                    "dlc_act_id": "112997",
                    "dlc_act_status": "2",
                    "dlc_is_free": "0",
                    "dlc_lottery_id": "112998",
                    "dlc_lottery_sale_quantity": "17786",
                    "dlc_lottery_type": "1",
                    "dlc_sale_end_time": "2114406245",
                    "dlc_sale_mode": "1",
                    "dlc_sale_start_time": "1780747200",
                    "dlc_surplus_stock": "0",
                    "image_cover": "https://i0.hdslb.com/bfs/garb/766075a17f5784edc0516e3d0e1876d1c88a68a5.jpg",
                    "sale_bp_forever_raw": "990",
                    "type": "dlc_act"
                },
                "current_activity": null,
                "next_activity": null,
                "current_sources": null,
                "finish_sources": null,
                "sale_left_time": -1784539463,
                "sale_time_end": -1784539463,
                "sale_surplus": 0,
                "sale_count_desc": "1万+",
                "total_count_desc": "已售1万+份",
                "tag": "",
                "jump_link": "https://www.bilibili.com/h5/mall/digital-card/home?-Abrowser=live&act_id=112997&hybrid_set_header=2&lottery_id=112998",
                "sales_mode": 0,
                "tracking_info": ""
            }
        ],
        "pn": 1,
        "ps": 20,
        "total": 9
    }
}
```

