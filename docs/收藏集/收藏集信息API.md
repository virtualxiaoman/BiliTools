## 收藏集信息API

> https://api.bilibili.com/x/vas/dlc_act/lottery_home_detail

*请求方式: GET*

**URL参数:**

| 参数名     | 类型 | 内容         | 必要性 | 备注             |
| ---------- | ---- | ------------ | ------ | ---------------- |
| act_id     | int  | 收藏集活动id | 必要   |                  |
| lottery_id | int  | 收藏集抽奖id | 不必要 | 但缺了不返回数据 |

**JSON回复:**

根对象:

| 字段    | 类型 | 内容     | 备注     |
| ------- | ---- | -------- | -------- |
| code    | num  | 返回值   | 0：成功  |
| message | str  | 错误信息 | 默认为 0 |
| ttl     | num  | 1        |          |
| data    | obj  | 返回数据 |          |

`data` 对象:

| 字段              | 类型  | 内容             | 备注 |
| ----------------- | ----- | ---------------- | ---- |
| lottery_id        | int   | 收藏集抽奖id     |      |
| name              | str   | 收藏集抽奖名称   |      |
| item_list         | array | 可抽出的物品列表 |      |
| collect_list      | obj   | 见下方           |      |
| button_bubble     | null  | 未知             |      |
| guide_info        | null  | 未知             |      |
| is_booked         | int   | 未知             |      |
| total_book_cnt    | int   | 未知             |      |
| is_fission        | int   | 未知             |      |
| physical_exchange | int   | 未知             |      |

`data` 中的 `item_list` 数组中的对象:

| 字段      | 类型 | 内容     | 备注                      |
| --------- | ---- | -------- | ------------------------- |
| item_type | int  | 物品类型 | 目前只拿到个1, 其他值未知 |
| card_info | obj  | 见下方   |                           |

`item_list` 数组中的对象中的 `card_info` 对象:

| 字段                    | 类型  | 内容                | 备注   |
| ----------------------- | ----- | ------------------- | ------ |
| card_type_id            | int   | 该卡片id            |        |
| card_name               | str   | 该卡片名称          |        |
| card_img                | str   | 该卡片图片          | 无水印 |
| card_type               | int   | int                 | 未知   |
| video_list              | array | 该卡片动态视频      | 无水印 |
| is_physical_orientation | int   | 该卡片旋转方向      |        |
| card_scarcity           | int   | 该卡片稀有度        |        |
| is_mute                 | int   | 该卡片是否静音      |        |
| width                   | int   | 该卡片像素宽度      |        |
| height                  | int   | 该卡片像素高度      |        |
| card_ext_text           | str   | ?该卡片文件名字符串 |        |
| card_img_download       | str   | 该卡片图片          | 有水印 |
| video_list_download     | array | 该卡片动态视频      | 有水印 |
| subtitles_url           | 未知  |                     |        |
| play                    | null  | 未知                |        |
| tag                     | null  | 未知                |        |
| card_sub_type           | int   | 未知                |        |
| is_new_tag              | int   | 未知                |        |
| is_up_tag               | int   | 未知                |        |
| is_limited_card         | int   | 未知                |        |
| stock_info              | null  | 未知                |        |

`data` 中的 `collect_list` 对象:

| 字段          | 类型  | 内容   | 备注 |
| ------------- | ----- | ------ | ---- |
| collect_infos | array | 见下方 |      |
| collect_chain | null  | 未知   |      |

`collect_list` 中的 `collect_infos` 数组中的对象：

| 字段                       | 类型 | 内容           | 备注        |
| -------------------------- | ---- | -------------- | ----------- |
| collect_id                 | int  | 收集品id       |             |
| start_time                 | int  | 开始时间       |             |
| end_time                   | int  | 结束时间       |             |
| redeem_text                | str  | 兑换条件       |             |
| redeem_item_type           | int  | 兑换物类型     |             |
| redeem_item_id             | str  | 兑换物id       |             |
| redeem_item_name           | str  | 兑换物名称     |             |
| redeem_item_image          | str  | 兑换物预览图片 |             |
| owned_item_amount          | int  | 拥有的数量     |             |
| require_item_amount        | int  | 需要的数量     |             |
| has_redeemed_cnt           | int  | 兑换次数       |             |
| effective_forever          | int  | 是否永久有效   |             |
| redeem_item_image_download | str  | 未知           |             |
| card_item                  | obj  | 见下方         | 有时为 null |
| jump_url                   | str  | ?跳转链接      |             |
| redeem_cond_type           | str  | 当前兑换状态   |             |
| remain_stock               | int  | 当前库存       |             |
| total_stock                | int  | 总库存         |             |
| lottery_id                 | int  | 抽奖id         |             |
| reward_tag                 | str  | 奖励显示标签   |             |
| redeem_detail_image        | str  | 兑换详情图片   |             |
| redeem_detail_videos       | null | 未知           |             |
| sort                       | int  | 排序           |             |
| redeem_items_optional      | null | 未知           |             |
| unlock_condition           | obj  | 见下方         |             |

`collect_infos` 数组中的对象中的 `card_item` 对象:

| 字段            | 类型 | 内容 | 备注 |
| --------------- | ---- | ---- | ---- |
| card_type_info  | null |      |      |
| card_asset_info | null |      |      |
| play            | null |      |      |
| tag             | null |      |      |

`collect_infos` 数组中的对象中的 `unlock_condition` 对象:

| 字段              | 类型 | 内容      | 备注 |
| ----------------- | ---- | --------- | ---- |
| unlocked          | bool | 是否解锁  |      |
| lock_type         | int  | 解锁类型  |      |
| expire_at         | int  | 过期与    |      |
| unlocked_at       | int  | 解锁于    |      |
| unlock_threshold  | int  | ?解锁起点 |      |
| current_threshold | int  | ?当前起点 |      |

**示例:**

```shell
curl -G --url 'https://api.bilibili.com/x/vas/dlc_act/lottery_home_detail' \
--url-query 'act_id=111106' \
--url-query 'lottery_id=111107'
```

返回数据

```json
{
    "code": 0,
    "message": "0",
    "ttl": 1,
    "data": {
        "lottery_id": 111107,
        "name": "未来有你魔法星夜",
        "item_list": [
            {
                "item_type": 1,
                "card_info": {
                    "card_type_id": 1766130192002,
                    "card_name": "夜行奇术师",
                    "card_img": "https://i0.hdslb.com/bfs/garb/open/c8aaaf9807f38620befd115fd4c6e7e694f26951.png",
                    "card_type": 2,
                    "video_list": [
                        "https://upos-sz-mirrorcos.bilivideo.com/panguxcodeboss/wb/ra/_00003mvwdlsbxpyb82jydh9b3iprawb-1-162111110023.mp4?e=ig8euxZM2rNcNbdlhoNvNC8BqJIzNbfq9rVEuxTEnE8L5F6VnEsSTx0vkX8fqJeYTj_lta53NCM=&uipk=5&nbs=1&deadline=1784547441&gen=playurlv2&os=cosbv&oi=1996673726&trid=336e243201cb437e886c70f80a1f7561B&mid=0&platform=html5&og=cos&upsig=9dea0aa3d36866dc8fe9fffecabb381a&uparams=e,uipk,nbs,deadline,gen,os,oi,trid,mid,platform,og&bvc=vod&nettype=0&orderid=0,3&logo=00000000&f=B_0_0",
                        "https://upos-sz-mirrorcos.bilivideo.com/panguxcodeboss/wb/ra/_00003mvwdlsbxpyb82jydh9b3iprawb-1-162111110023.mp4?e=ig8euxZM2rNcNbdlhoNvNC8BqJIzNbfq9rVEuxTEnE8L5F6VnEsSTx0vkX8fqJeYTj_lta53NCM=&uipk=5&nbs=1&deadline=1784547441&gen=playurlv2&os=cosbv&oi=1996673726&trid=336e243201cb437e886c70f80a1f7561B&mid=0&platform=html5&og=cos&upsig=9dea0aa3d36866dc8fe9fffecabb381a&uparams=e,uipk,nbs,deadline,gen,os,oi,trid,mid,platform,og&bvc=vod&nettype=0&orderid=1,3&logo=00000000&f=B_0_0",
                        "https://upos-sz-mirrorcos.bilivideo.com/panguxcodeboss/wb/ra/_00003mvwdlsbxpyb82jydh9b3iprawb-1-162111110023.mp4?e=ig8euxZM2rNcNbdlhoNvNC8BqJIzNbfq9rVEuxTEnE8L5F6VnEsSTx0vkX8fqJeYTj_lta53NCM=&uipk=5&nbs=1&deadline=1784547441&gen=playurlv2&os=cosbv&oi=1996673726&trid=336e243201cb437e886c70f80a1f7561B&mid=0&platform=html5&og=cos&upsig=9dea0aa3d36866dc8fe9fffecabb381a&uparams=e,uipk,nbs,deadline,gen,os,oi,trid,mid,platform,og&bvc=vod&nettype=0&orderid=2,3&logo=00000000&f=B_0_0"
                    ],
                    "is_physical_orientation": 0,
                    "card_scarcity": 40,
                    "is_mute": 0,
                    "width": 1242,
                    "height": 1863,
                    "card_ext_text": "",
                    "card_img_download": "https://i0.hdslb.com/bfs/garb/watermark/cb69e69fedc08a57c6407f15f3746fcf33928ba5.png",
                    "video_list_download": [
                        "https://upos-sz-mirror08c.bilivideo.com/panguxcodeboss/digital_watermarkab/su/_000003rjgmbr4d0bk2inbwf95y3suab-teaser.mp4?e=ig8euxZM2rNcNbdlhoNvNC8BqJIzNbfq9rVEuxTEnE8L5F6VnEsSTx0vkX8fqJeYTj_lta53NCM=&uipk=5&nbs=1&deadline=1784547441&gen=playurlv2&os=08cbv&oi=1996673726&trid=336e243201cb437e886c70f80a1f7561B&mid=0&platform=html5&og=hw&upsig=69f190e69fbe1c8911ffe7369b38d09c&uparams=e,uipk,nbs,deadline,gen,os,oi,trid,mid,platform,og&bvc=vod&nettype=0&orderid=0,3&logo=00000000&f=B_0_0",
                        "https://upos-sz-mirror08c.bilivideo.com/panguxcodeboss/digital_watermarkab/su/_000003rjgmbr4d0bk2inbwf95y3suab-teaser.mp4?e=ig8euxZM2rNcNbdlhoNvNC8BqJIzNbfq9rVEuxTEnE8L5F6VnEsSTx0vkX8fqJeYTj_lta53NCM=&uipk=5&nbs=1&deadline=1784547441&gen=playurlv2&os=08cbv&oi=1996673726&trid=336e243201cb437e886c70f80a1f7561B&mid=0&platform=html5&og=hw&upsig=69f190e69fbe1c8911ffe7369b38d09c&uparams=e,uipk,nbs,deadline,gen,os,oi,trid,mid,platform,og&bvc=vod&nettype=0&orderid=1,3&logo=00000000&f=B_0_0",
                        "https://upos-sz-mirror08c.bilivideo.com/panguxcodeboss/digital_watermarkab/su/_000003rjgmbr4d0bk2inbwf95y3suab-teaser.mp4?e=ig8euxZM2rNcNbdlhoNvNC8BqJIzNbfq9rVEuxTEnE8L5F6VnEsSTx0vkX8fqJeYTj_lta53NCM=&uipk=5&nbs=1&deadline=1784547441&gen=playurlv2&os=08cbv&oi=1996673726&trid=336e243201cb437e886c70f80a1f7561B&mid=0&platform=html5&og=hw&upsig=69f190e69fbe1c8911ffe7369b38d09c&uparams=e,uipk,nbs,deadline,gen,os,oi,trid,mid,platform,og&bvc=vod&nettype=0&orderid=2,3&logo=00000000&f=B_0_0"
                    ],
                    "subtitles_url": "",
                    "play": null,
                    "tag": null,
                    "card_sub_type": 0,
                    "is_new_tag": 0,
                    "is_up_tag": 0,
                    "is_limited_card": 0,
                    "stock_info": null,
                    "meta_info": null,
                    "own_count": 0
                }
            },
            {
                "item_type": 1,
                "card_info": {
                    "card_type_id": 1766130192010,
                    "card_name": "星盘秘境之庭",
                    "card_img": "https://i0.hdslb.com/bfs/garb/open/1addeab7fd418f386b7a6ab9201fd77748955654.png",
                    "card_type": 2,
                    "video_list": [
                        "https://upos-sz-mirror08c.bilivideo.com/panguxcodeboss/3b/dn/_00000mt4i9gk2s2d82pfco15dwgdn3b-1-162111110023.mp4?e=ig8euxZM2rNcNbdlhoNvNC8BqJIzNbfq9rVEuxTEnE8L5F6VnEsSTx0vkX8fqJeYTj_lta53NCM=&uipk=5&nbs=1&deadline=1784547441&gen=playurlv2&os=08cbv&oi=1996673726&trid=336e243201cb437e886c70f80a1f7561B&mid=0&platform=html5&og=hw&upsig=d21b9a7d620a9d64d30aaefcebece9c7&uparams=e,uipk,nbs,deadline,gen,os,oi,trid,mid,platform,og&bvc=vod&nettype=0&orderid=0,3&logo=00000000&f=B_0_0",
                        "https://upos-sz-mirror08c.bilivideo.com/panguxcodeboss/3b/dn/_00000mt4i9gk2s2d82pfco15dwgdn3b-1-162111110023.mp4?e=ig8euxZM2rNcNbdlhoNvNC8BqJIzNbfq9rVEuxTEnE8L5F6VnEsSTx0vkX8fqJeYTj_lta53NCM=&uipk=5&nbs=1&deadline=1784547441&gen=playurlv2&os=08cbv&oi=1996673726&trid=336e243201cb437e886c70f80a1f7561B&mid=0&platform=html5&og=hw&upsig=d21b9a7d620a9d64d30aaefcebece9c7&uparams=e,uipk,nbs,deadline,gen,os,oi,trid,mid,platform,og&bvc=vod&nettype=0&orderid=1,3&logo=00000000&f=B_0_0",
                        "https://upos-sz-mirror08c.bilivideo.com/panguxcodeboss/3b/dn/_00000mt4i9gk2s2d82pfco15dwgdn3b-1-162111110023.mp4?e=ig8euxZM2rNcNbdlhoNvNC8BqJIzNbfq9rVEuxTEnE8L5F6VnEsSTx0vkX8fqJeYTj_lta53NCM=&uipk=5&nbs=1&deadline=1784547441&gen=playurlv2&os=08cbv&oi=1996673726&trid=336e243201cb437e886c70f80a1f7561B&mid=0&platform=html5&og=hw&upsig=d21b9a7d620a9d64d30aaefcebece9c7&uparams=e,uipk,nbs,deadline,gen,os,oi,trid,mid,platform,og&bvc=vod&nettype=0&orderid=2,3&logo=00000000&f=B_0_0"
                    ],
                    "is_physical_orientation": 0,
                    "card_scarcity": 30,
                    "is_mute": 0,
                    "width": 1242,
                    "height": 1863,
                    "card_ext_text": "",
                    "card_img_download": "https://i0.hdslb.com/bfs/garb/watermark/ed66581b93c16db18b94f72bfd3024439efd2213.png",
                    "video_list_download": [
                        "https://upos-sz-mirror08c.bilivideo.com/panguxcodeboss/digital_watermark6b/ak/_00000vkbh7vjrzpfo21vv3qy18jak6b-teaser.mp4?e=ig8euxZM2rNcNbdlhoNvNC8BqJIzNbfq9rVEuxTEnE8L5F6VnEsSTx0vkX8fqJeYTj_lta53NCM=&uipk=5&nbs=1&deadline=1784547441&gen=playurlv2&os=08cbv&oi=1996673726&trid=336e243201cb437e886c70f80a1f7561B&mid=0&platform=html5&og=hw&upsig=947fbe421d93d2c05333cdeed4562e74&uparams=e,uipk,nbs,deadline,gen,os,oi,trid,mid,platform,og&bvc=vod&nettype=0&orderid=0,3&logo=00000000&f=B_0_0",
                        "https://upos-sz-mirror08c.bilivideo.com/panguxcodeboss/digital_watermark6b/ak/_00000vkbh7vjrzpfo21vv3qy18jak6b-teaser.mp4?e=ig8euxZM2rNcNbdlhoNvNC8BqJIzNbfq9rVEuxTEnE8L5F6VnEsSTx0vkX8fqJeYTj_lta53NCM=&uipk=5&nbs=1&deadline=1784547441&gen=playurlv2&os=08cbv&oi=1996673726&trid=336e243201cb437e886c70f80a1f7561B&mid=0&platform=html5&og=hw&upsig=947fbe421d93d2c05333cdeed4562e74&uparams=e,uipk,nbs,deadline,gen,os,oi,trid,mid,platform,og&bvc=vod&nettype=0&orderid=1,3&logo=00000000&f=B_0_0",
                        "https://upos-sz-mirror08c.bilivideo.com/panguxcodeboss/digital_watermark6b/ak/_00000vkbh7vjrzpfo21vv3qy18jak6b-teaser.mp4?e=ig8euxZM2rNcNbdlhoNvNC8BqJIzNbfq9rVEuxTEnE8L5F6VnEsSTx0vkX8fqJeYTj_lta53NCM=&uipk=5&nbs=1&deadline=1784547441&gen=playurlv2&os=08cbv&oi=1996673726&trid=336e243201cb437e886c70f80a1f7561B&mid=0&platform=html5&og=hw&upsig=947fbe421d93d2c05333cdeed4562e74&uparams=e,uipk,nbs,deadline,gen,os,oi,trid,mid,platform,og&bvc=vod&nettype=0&orderid=2,3&logo=00000000&f=B_0_0"
                    ],
                    "subtitles_url": "",
                    "play": null,
                    "tag": null,
                    "card_sub_type": 0,
                    "is_new_tag": 0,
                    "is_up_tag": 0,
                    "is_limited_card": 0,
                    "stock_info": null,
                    "meta_info": null,
                    "own_count": 0
                }
            },
            {
                "item_type": 1,
                "card_info": {
                    "card_type_id": 1766130192003,
                    "card_name": "星光宣礼",
                    "card_img": "https://i0.hdslb.com/bfs/garb/open/114b67d42e50e306311b6428bdcc113cea1b40f3.png",
                    "card_type": 2,
                    "video_list": [
                        "https://upos-sz-mirrorcos.bilivideo.com/panguxcodeboss/cb/lo/_00002j7oi8sh1tho32itz3apkqxlocb-1-162210110000.mp4?e=ig8euxZM2rNcNbdlhoNvNC8BqJIzNbfq9rVEuxTEnE8L5F6VnEsSTx0vkX8fqJeYTj_lta53NCM=&uipk=5&nbs=1&deadline=1784547441&gen=playurlv2&os=cosbv&oi=1996673726&trid=336e243201cb437e886c70f80a1f7561B&mid=0&platform=html5&og=cos&upsig=67f4aeefa69dc1e668b11339005d93d7&uparams=e,uipk,nbs,deadline,gen,os,oi,trid,mid,platform,og&bvc=vod&nettype=0&orderid=0,3&logo=00000000&f=B_0_0",
                        "https://upos-sz-mirrorcos.bilivideo.com/panguxcodeboss/cb/lo/_00002j7oi8sh1tho32itz3apkqxlocb-1-162210110000.mp4?e=ig8euxZM2rNcNbdlhoNvNC8BqJIzNbfq9rVEuxTEnE8L5F6VnEsSTx0vkX8fqJeYTj_lta53NCM=&uipk=5&nbs=1&deadline=1784547441&gen=playurlv2&os=cosbv&oi=1996673726&trid=336e243201cb437e886c70f80a1f7561B&mid=0&platform=html5&og=cos&upsig=67f4aeefa69dc1e668b11339005d93d7&uparams=e,uipk,nbs,deadline,gen,os,oi,trid,mid,platform,og&bvc=vod&nettype=0&orderid=1,3&logo=00000000&f=B_0_0",
                        "https://upos-sz-mirrorcos.bilivideo.com/panguxcodeboss/cb/lo/_00002j7oi8sh1tho32itz3apkqxlocb-1-162210110000.mp4?e=ig8euxZM2rNcNbdlhoNvNC8BqJIzNbfq9rVEuxTEnE8L5F6VnEsSTx0vkX8fqJeYTj_lta53NCM=&uipk=5&nbs=1&deadline=1784547441&gen=playurlv2&os=cosbv&oi=1996673726&trid=336e243201cb437e886c70f80a1f7561B&mid=0&platform=html5&og=cos&upsig=67f4aeefa69dc1e668b11339005d93d7&uparams=e,uipk,nbs,deadline,gen,os,oi,trid,mid,platform,og&bvc=vod&nettype=0&orderid=2,3&logo=00000000&f=B_0_0"
                    ],
                    "is_physical_orientation": 0,
                    "card_scarcity": 20,
                    "is_mute": 1,
                    "width": 1242,
                    "height": 1863,
                    "card_ext_text": "",
                    "card_img_download": "https://i0.hdslb.com/bfs/garb/watermark/1d613c8e58c3d15f9031a53be6d54aed0555e12b.png",
                    "video_list_download": [
                        "https://upos-sz-mirrorcos.bilivideo.com/panguxcodeboss/digital_watermarksb/l6/_00001edctlbhjbykg203e0tvauil6sb-teaser.mp4?e=ig8euxZM2rNcNbdlhoNvNC8BqJIzNbfq9rVEuxTEnE8L5F6VnEsSTx0vkX8fqJeYTj_lta53NCM=&uipk=5&nbs=1&deadline=1784547441&gen=playurlv2&os=cosbv&oi=1996673726&trid=336e243201cb437e886c70f80a1f7561B&mid=0&platform=html5&og=cos&upsig=10f73a22d36d14260716c2bd9b930183&uparams=e,uipk,nbs,deadline,gen,os,oi,trid,mid,platform,og&bvc=vod&nettype=0&orderid=0,3&logo=00000000&f=B_0_0",
                        "https://upos-sz-mirrorcos.bilivideo.com/panguxcodeboss/digital_watermarksb/l6/_00001edctlbhjbykg203e0tvauil6sb-teaser.mp4?e=ig8euxZM2rNcNbdlhoNvNC8BqJIzNbfq9rVEuxTEnE8L5F6VnEsSTx0vkX8fqJeYTj_lta53NCM=&uipk=5&nbs=1&deadline=1784547441&gen=playurlv2&os=cosbv&oi=1996673726&trid=336e243201cb437e886c70f80a1f7561B&mid=0&platform=html5&og=cos&upsig=10f73a22d36d14260716c2bd9b930183&uparams=e,uipk,nbs,deadline,gen,os,oi,trid,mid,platform,og&bvc=vod&nettype=0&orderid=1,3&logo=00000000&f=B_0_0",
                        "https://upos-sz-mirrorcos.bilivideo.com/panguxcodeboss/digital_watermarksb/l6/_00001edctlbhjbykg203e0tvauil6sb-teaser.mp4?e=ig8euxZM2rNcNbdlhoNvNC8BqJIzNbfq9rVEuxTEnE8L5F6VnEsSTx0vkX8fqJeYTj_lta53NCM=&uipk=5&nbs=1&deadline=1784547441&gen=playurlv2&os=cosbv&oi=1996673726&trid=336e243201cb437e886c70f80a1f7561B&mid=0&platform=html5&og=cos&upsig=10f73a22d36d14260716c2bd9b930183&uparams=e,uipk,nbs,deadline,gen,os,oi,trid,mid,platform,og&bvc=vod&nettype=0&orderid=2,3&logo=00000000&f=B_0_0"
                    ],
                    "subtitles_url": "",
                    "play": null,
                    "tag": null,
                    "card_sub_type": 0,
                    "is_new_tag": 0,
                    "is_up_tag": 0,
                    "is_limited_card": 0,
                    "stock_info": null,
                    "meta_info": null,
                    "own_count": 0
                }
            },
            {
                "item_type": 1,
                "card_info": {
                    "card_type_id": 1766130192004,
                    "card_name": "司灯引路",
                    "card_img": "https://i0.hdslb.com/bfs/garb/open/5b8fce71266f1bdec5b30df9fc9421bdd55a4d0b.png",
                    "card_type": 1,
                    "video_list": null,
                    "is_physical_orientation": 0,
                    "card_scarcity": 10,
                    "is_mute": 0,
                    "width": 1242,
                    "height": 1863,
                    "card_ext_text": "",
                    "card_img_download": "https://i0.hdslb.com/bfs/garb/watermark/4e53907768c0740cd7a4ab0f0a6813114b704f3c.png",
                    "video_list_download": null,
                    "subtitles_url": "",
                    "play": null,
                    "tag": null,
                    "card_sub_type": 0,
                    "is_new_tag": 0,
                    "is_up_tag": 0,
                    "is_limited_card": 0,
                    "stock_info": null,
                    "meta_info": null,
                    "own_count": 0
                }
            },
            {
                "item_type": 1,
                "card_info": {
                    "card_type_id": 1766130192005,
                    "card_name": "乐堡指挥",
                    "card_img": "https://i0.hdslb.com/bfs/garb/open/7f264f22578cdd5e9f9bf078bf4f2ab52e53b9a1.png",
                    "card_type": 1,
                    "video_list": null,
                    "is_physical_orientation": 0,
                    "card_scarcity": 10,
                    "is_mute": 0,
                    "width": 1242,
                    "height": 1863,
                    "card_ext_text": "",
                    "card_img_download": "https://i0.hdslb.com/bfs/garb/watermark/68f96eb4894034ba6e0960c104a3579712674bed.png",
                    "video_list_download": null,
                    "subtitles_url": "",
                    "play": null,
                    "tag": null,
                    "card_sub_type": 0,
                    "is_new_tag": 0,
                    "is_up_tag": 0,
                    "is_limited_card": 0,
                    "stock_info": null,
                    "meta_info": null,
                    "own_count": 0
                }
            },
            {
                "item_type": 1,
                "card_info": {
                    "card_type_id": 1766130192006,
                    "card_name": "秉烛乐行",
                    "card_img": "https://i0.hdslb.com/bfs/garb/open/27054395b9239b7027b2ac971d47402ca6f3e926.png",
                    "card_type": 1,
                    "video_list": null,
                    "is_physical_orientation": 0,
                    "card_scarcity": 10,
                    "is_mute": 0,
                    "width": 1242,
                    "height": 1863,
                    "card_ext_text": "",
                    "card_img_download": "https://i0.hdslb.com/bfs/garb/watermark/0e4c997bbe3dbc3438eead710544f7ee7e5bc796.png",
                    "video_list_download": null,
                    "subtitles_url": "",
                    "play": null,
                    "tag": null,
                    "card_sub_type": 0,
                    "is_new_tag": 0,
                    "is_up_tag": 0,
                    "is_limited_card": 0,
                    "stock_info": null,
                    "meta_info": null,
                    "own_count": 0
                }
            },
            {
                "item_type": 1,
                "card_info": {
                    "card_type_id": 1766130192007,
                    "card_name": "启明序曲",
                    "card_img": "https://i0.hdslb.com/bfs/garb/open/c17ca3b76dc774220ed7748a482ea4d3967f44ca.png",
                    "card_type": 1,
                    "video_list": null,
                    "is_physical_orientation": 0,
                    "card_scarcity": 10,
                    "is_mute": 0,
                    "width": 1242,
                    "height": 1863,
                    "card_ext_text": "",
                    "card_img_download": "https://i0.hdslb.com/bfs/garb/watermark/b516dd085d64e47f88789f0ea779fafd9ab294cf.png",
                    "video_list_download": null,
                    "subtitles_url": "",
                    "play": null,
                    "tag": null,
                    "card_sub_type": 0,
                    "is_new_tag": 0,
                    "is_up_tag": 0,
                    "is_limited_card": 0,
                    "stock_info": null,
                    "meta_info": null,
                    "own_count": 0
                }
            },
            {
                "item_type": 1,
                "card_info": {
                    "card_type_id": 1766130192008,
                    "card_name": "晶辉加冕",
                    "card_img": "https://i0.hdslb.com/bfs/garb/open/e9d8e433c645a59a7bc9d83cc93f772da396abaf.png",
                    "card_type": 1,
                    "video_list": null,
                    "is_physical_orientation": 0,
                    "card_scarcity": 10,
                    "is_mute": 0,
                    "width": 1242,
                    "height": 1863,
                    "card_ext_text": "",
                    "card_img_download": "https://i0.hdslb.com/bfs/garb/watermark/85e6520600db02a833137b6e71e4b283e9aff5a5.png",
                    "video_list_download": null,
                    "subtitles_url": "",
                    "play": null,
                    "tag": null,
                    "card_sub_type": 0,
                    "is_new_tag": 0,
                    "is_up_tag": 0,
                    "is_limited_card": 0,
                    "stock_info": null,
                    "meta_info": null,
                    "own_count": 0
                }
            },
            {
                "item_type": 1,
                "card_info": {
                    "card_type_id": 1766130192009,
                    "card_name": "kirakira魔法",
                    "card_img": "https://i0.hdslb.com/bfs/garb/open/eb8d888935b393509eb967cb91e3cafd14a7835e.png",
                    "card_type": 1,
                    "video_list": null,
                    "is_physical_orientation": 0,
                    "card_scarcity": 10,
                    "is_mute": 0,
                    "width": 1242,
                    "height": 1863,
                    "card_ext_text": "",
                    "card_img_download": "https://i0.hdslb.com/bfs/garb/watermark/4e87c429a1c6059f0771ed5a1a5033ba011decfb.png",
                    "video_list_download": null,
                    "subtitles_url": "",
                    "play": null,
                    "tag": null,
                    "card_sub_type": 0,
                    "is_new_tag": 0,
                    "is_up_tag": 0,
                    "is_limited_card": 0,
                    "stock_info": null,
                    "meta_info": null,
                    "own_count": 0
                }
            }
        ],
        "collect_list": {
            "collect_infos": [
                {
                    "collect_id": 0,
                    "start_time": 1766203200,
                    "end_time": 2114406245,
                    "redeem_text": "1抽必得勋章，可应用为评论背景&动态卡片",
                    "redeem_item_type": 1001,
                    "redeem_item_id": "",
                    "redeem_item_name": "初音魔法星夜勋章",
                    "redeem_item_image": "https://i0.hdslb.com/bfs/garb/open/dd54cac51da5ecf456407247bbc4a0e5d2fd4dbd.png",
                    "owned_item_amount": 0,
                    "require_item_amount": 1,
                    "has_redeemed_cnt": 0,
                    "effective_forever": 1,
                    "redeem_item_image_download": "",
                    "card_item": null,
                    "jump_url": "",
                    "redeem_cond_type": "",
                    "remain_stock": 0,
                    "total_stock": -1,
                    "lottery_id": 0,
                    "reward_tag": "",
                    "redeem_detail_image": "https://i0.hdslb.com/bfs/garb/c07df2850b2cc46307d7da1a2c56a6af740b01bf.png",
                    "redeem_detail_videos": null,
                    "sort": 0,
                    "redeem_items_optional": null,
                    "unlock_condition": {
                        "unlocked": true,
                        "lock_type": 0,
                        "expire_at": 0,
                        "unlocked_at": 0,
                        "unlock_threshold": 0,
                        "current_threshold": 0
                    },
                    "redeem_item_optional_list": null,
                    "redeem_count": null,
                    "rank_info": null,
                    "redeem_btn_text": "差1抽点亮",
                    "anchor_id": 1001111106,
                    "preview_type": 2,
                    "redeem_item_type_name": "评论背景",
                    "redeem_item_status": 0,
                    "window_info": null,
                    "data_ext": {
                        "color": "#EFBA90"
                    }
                },
                {
                    "collect_id": 111109,
                    "start_time": 1766203200,
                    "end_time": 2114406245,
                    "redeem_text": "未来有你魔法星夜卡池抽到任意1张隐藏款立绘即可领取",
                    "redeem_item_type": 3,
                    "redeem_item_id": "1765867934001",
                    "redeem_item_name": "未来有你·魔法星夜头像框",
                    "redeem_item_image": "https://i0.hdslb.com/bfs/garb/open/46bc8f0d70eb12b0430f0ee1896dd77f8617a9af.png",
                    "owned_item_amount": 0,
                    "require_item_amount": 1,
                    "has_redeemed_cnt": 0,
                    "effective_forever": 1,
                    "redeem_item_image_download": "",
                    "card_item": {
                        "card_type_info": null,
                        "play": null,
                        "tag": null,
                        "card_asset_info": null
                    },
                    "jump_url": "",
                    "redeem_cond_type": "scarcity",
                    "remain_stock": -1,
                    "total_stock": -1,
                    "lottery_id": 111107,
                    "reward_tag": "",
                    "redeem_detail_image": "https://i0.hdslb.com/bfs/garb/open/46bc8f0d70eb12b0430f0ee1896dd77f8617a9af.png",
                    "redeem_detail_videos": null,
                    "sort": 2,
                    "redeem_items_optional": null,
                    "unlock_condition": {
                        "unlocked": true,
                        "lock_type": 0,
                        "expire_at": 0,
                        "unlocked_at": 0,
                        "unlock_threshold": 0,
                        "current_threshold": 0
                    },
                    "redeem_item_optional_list": null,
                    "redeem_count": {
                        "has_redeem_count": 0,
                        "redeem_count": 2,
                        "redeem_count_type": 0
                    },
                    "rank_info": null,
                    "redeem_btn_text": "1张隐藏款领取",
                    "anchor_id": 111109,
                    "preview_type": 2,
                    "redeem_item_type_name": "头像挂件",
                    "redeem_item_status": 0,
                    "window_info": null,
                    "data_ext": null
                }
            ],
            "collect_chain": [
                {
                    "collect_id": 0,
                    "start_time": 1766203200,
                    "end_time": 2114406245,
                    "redeem_text": "1抽",
                    "redeem_item_type": 1000,
                    "redeem_item_id": "",
                    "redeem_item_name": "钻石头像背景",
                    "redeem_item_image": "https://i0.hdslb.com/bfs/garb/open/5b8fce71266f1bdec5b30df9fc9421bdd55a4d0b.png",
                    "owned_item_amount": 0,
                    "require_item_amount": 1,
                    "has_redeemed_cnt": 0,
                    "effective_forever": 0,
                    "redeem_item_image_download": "",
                    "card_item": null,
                    "jump_url": "",
                    "redeem_cond_type": "",
                    "remain_stock": 0,
                    "total_stock": -1,
                    "lottery_id": 111107,
                    "reward_tag": "",
                    "redeem_detail_image": "https://i0.hdslb.com/bfs/garb/41a48eb991aab538609d9fbd869aef6bee84b08f.png",
                    "redeem_detail_videos": null,
                    "sort": 0,
                    "redeem_items_optional": null,
                    "unlock_condition": null,
                    "redeem_item_optional_list": null,
                    "redeem_count": null,
                    "rank_info": null,
                    "redeem_btn_text": "",
                    "anchor_id": 0,
                    "preview_type": 0,
                    "redeem_item_type_name": "",
                    "redeem_item_status": 0,
                    "window_info": null,
                    "data_ext": null
                },
                {
                    "collect_id": 111108,
                    "start_time": 1766203200,
                    "end_time": 2114406245,
                    "redeem_text": "未来有你魔法星夜卡池完成2抽即可领取",
                    "redeem_item_type": 2,
                    "redeem_item_id": "1765868919001",
                    "redeem_item_name": "表情包",
                    "redeem_item_image": "https://i0.hdslb.com/bfs/garb/9dc2cbb97376c34648bba01be44643bee7313e77.png",
                    "owned_item_amount": 0,
                    "require_item_amount": 2,
                    "has_redeemed_cnt": 0,
                    "effective_forever": 1,
                    "redeem_item_image_download": "",
                    "card_item": {
                        "card_type_info": null,
                        "play": null,
                        "tag": null,
                        "card_asset_info": null
                    },
                    "jump_url": "",
                    "redeem_cond_type": "lottery_num",
                    "remain_stock": -1,
                    "total_stock": -1,
                    "lottery_id": 111107,
                    "reward_tag": "",
                    "redeem_detail_image": "https://i0.hdslb.com/bfs/garb/9dc2cbb97376c34648bba01be44643bee7313e77.png",
                    "redeem_detail_videos": null,
                    "sort": 1,
                    "redeem_items_optional": null,
                    "unlock_condition": {
                        "unlocked": true,
                        "lock_type": 0,
                        "expire_at": 0,
                        "unlocked_at": 0,
                        "unlock_threshold": 0,
                        "current_threshold": 0
                    },
                    "redeem_item_optional_list": null,
                    "redeem_count": {
                        "has_redeem_count": 0,
                        "redeem_count": 2,
                        "redeem_count_type": 0
                    },
                    "rank_info": null,
                    "redeem_btn_text": "差2抽领取",
                    "anchor_id": 111108,
                    "preview_type": 2,
                    "redeem_item_type_name": "表情包",
                    "redeem_item_status": 0,
                    "window_info": null,
                    "data_ext": null
                },
                {
                    "collect_id": 111110,
                    "start_time": 1766203200,
                    "end_time": 2114406245,
                    "redeem_text": "未来有你魔法星夜卡池完成5抽即可领取",
                    "redeem_item_type": 5,
                    "redeem_item_id": "1765870054001&1765868795001&1765868727001&1765868762001",
                    "redeem_item_name": "动态主题套装",
                    "redeem_item_image": "https://i0.hdslb.com/bfs/garb/c557693b15cc4213f47e86f419b46c30bfedc608.png",
                    "owned_item_amount": 0,
                    "require_item_amount": 5,
                    "has_redeemed_cnt": 0,
                    "effective_forever": 1,
                    "redeem_item_image_download": "",
                    "card_item": {
                        "card_type_info": null,
                        "play": null,
                        "tag": null,
                        "card_asset_info": null
                    },
                    "jump_url": "",
                    "redeem_cond_type": "lottery_num",
                    "remain_stock": -1,
                    "total_stock": -1,
                    "lottery_id": 111107,
                    "reward_tag": "",
                    "redeem_detail_image": "https://i0.hdslb.com/bfs/baselabs/first_frame/57c2f48b-9c22-41cd-b9d5-ce975a72a4b7.png",
                    "redeem_detail_videos": [
                        "http://jssz-boss.hdslb.com/garb-live2d-resource/award_video/5ea82394-309f-4fab-bb82-b50455e9b0d0.mp4"
                    ],
                    "sort": 3,
                    "redeem_items_optional": null,
                    "unlock_condition": {
                        "unlocked": true,
                        "lock_type": 0,
                        "expire_at": 0,
                        "unlocked_at": 0,
                        "unlock_threshold": 0,
                        "current_threshold": 0
                    },
                    "redeem_item_optional_list": null,
                    "redeem_count": {
                        "has_redeem_count": 0,
                        "redeem_count": 2,
                        "redeem_count_type": 0
                    },
                    "rank_info": null,
                    "redeem_btn_text": "差5抽领取",
                    "anchor_id": 111110,
                    "preview_type": 2,
                    "redeem_item_type_name": "动态主题套装",
                    "redeem_item_status": 0,
                    "window_info": null,
                    "data_ext": null
                }
            ]
        },
        "button_bubble": [
            {
                "lottery_num": 5,
                "bubble_text": "获得主题套装"
            }
        ],
        "guide_info": {
            "title": "",
            "guide_content": "",
            "jump_url": ""
        },
        "is_booked": 0,
        "total_book_cnt": 2133,
        "is_fission": 1,
        "physical_exchange": 0,
        "act_rights_infos": [
            {
                "range_type": 2,
                "rights_type": 1,
                "resource": "https://i0.hdslb.com/bfs/garb/open/c8aaaf9807f38620befd115fd4c6e7e694f26951.png@0-0-1079-1079a",
                "extra": "{}"
            },
            {
                "range_type": 2,
                "rights_type": 2,
                "resource": "https://i0.hdslb.com/bfs/garb/open/c8aaaf9807f38620befd115fd4c6e7e694f26951.png@0-0-1079-1079a",
                "extra": "{}"
            },
            {
                "range_type": 2,
                "rights_type": 5,
                "resource": "https://i0.hdslb.com/bfs/vas_new/73bbc90f70dfda946683b851a5bbad0d85b66abb.webp",
                "extra": "{\"logo_mode\":1}"
            },
            {
                "range_type": 1,
                "rights_type": 3,
                "resource": "https://i0.hdslb.com/bfs/garb/open/c8aaaf9807f38620befd115fd4c6e7e694f26951.png@0-0-1079-1079a",
                "extra": "{}"
            },
            {
                "range_type": 2,
                "rights_type": 6,
                "resource": "https://i0.hdslb.com/bfs/garb/open/c8aaaf9807f38620befd115fd4c6e7e694f26951.png",
                "extra": "{}"
            },
            {
                "range_type": 1,
                "rights_type": 4,
                "resource": "https://i0.hdslb.com/bfs/garb/open/c8aaaf9807f38620befd115fd4c6e7e694f26951.png",
                "extra": "{}"
            },
            {
                "range_type": 1,
                "rights_type": 7,
                "resource": "https://i0.hdslb.com/bfs/garb/open/c8aaaf9807f38620befd115fd4c6e7e694f26951.png",
                "extra": "{}"
            }
        ],
        "upgrade_pool_desc": ""
    }
}
```

