"""收藏集奖励素材（含无水印动画）的回归测试。"""

from src.services.garb import GarbService


class _Session:
    def __init__(self):
        self.session = type(
            "RequestsSession", (), {"headers": {"Referer": "https://www.bilibili.com/"}}
        )()


def _reward_detail(*, include_plain_animation=True):
    animation = {
        "animation_backup_image": "https://cdn.example.com/animation-backup.png",
        "animation_first_frame": "https://cdn.example.com/animation-first.jpg",
    }
    if include_plain_animation:
        animation["animation_video_urls"] = [
            "https://cdn.example.com/no-watermark-1.mp4?orderid=1",
            "https://cdn.example.com/no-watermark-2.mp4?orderid=2",
        ]

    return {
        "cover": "https://cdn.example.com/collection-cover.jpg",
        "collect_list": {
            "collect_infos": [
                {
                    "collect_id": 114114,
                    "redeem_item_name": "纯蓝幻乐头像框",
                    "redeem_item_image": "https://cdn.example.com/avatar-frame.png",
                    "redeem_item_image_download": "https://cdn.example.com/avatar-frame-download.png",
                    "redeem_detail_image": "https://cdn.example.com/avatar-frame-detail.jpg",
                    "redeem_detail_videos": ["https://cdn.example.com/avatar-frame-detail.mp4"],
                    "redeem_item_optional_list": [
                        {"image": "https://cdn.example.com/optional-reward.png"},
                    ],
                    "card_item": {
                        "card_type_info": {
                            "content": {"animation": animation},
                            "watermark_animations": [
                                {"watermark_animation": "https://cdn.example.com/with-watermark.mp4"},
                            ],
                            "static_preview": "https://cdn.example.com/card-preview.webp",
                        },
                    },
                },
            ],
        },
    }


def test_collection_reward_resources_include_collect_infos_and_prefer_plain_animation():
    resources = GarbService(_Session()).list_resources(
        {"name": "纯蓝幻乐", "part_id": 0}, _reward_detail(), resource_types="collect_reward",
    )

    urls = [resource.url for resource in resources]
    assert urls == [
        "https://cdn.example.com/avatar-frame.png",
        "https://cdn.example.com/avatar-frame-download.png",
        "https://cdn.example.com/avatar-frame-detail.jpg",
        "https://cdn.example.com/avatar-frame-detail.mp4",
        "https://cdn.example.com/optional-reward.png",
        "https://cdn.example.com/no-watermark-1.mp4?orderid=1",
        "https://cdn.example.com/no-watermark-2.mp4?orderid=2",
        "https://cdn.example.com/animation-backup.png",
        "https://cdn.example.com/animation-first.jpg",
        "https://cdn.example.com/card-preview.webp",
    ]
    assert "https://cdn.example.com/with-watermark.mp4" not in urls
    assert {resource.category for resource in resources} == {"奖励素材"}
    assert any(resource.media_type == "collection_reward_video" for resource in resources)


def test_collection_reward_uses_watermarked_animation_only_as_fallback():
    resources = GarbService(_Session()).list_resources(
        {"name": "纯蓝幻乐", "part_id": 0},
        _reward_detail(include_plain_animation=False),
        resource_types="collect_reward",
    )

    urls = [resource.url for resource in resources]
    assert "https://cdn.example.com/with-watermark.mp4" in urls
    assert not any("no-watermark" in url for url in urls)


def test_collection_reward_filter_downloads_to_reward_directory(tmp_path, monkeypatch):
    calls = []

    def fake_download(url, path, headers=None, progress_cb=None):
        calls.append((url, path))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"asset")
        if progress_cb:
            progress_cb(1, 1)
        return 5

    monkeypatch.setattr("src.services.garb.download_stream", fake_download)
    results = GarbService(_Session()).download_item(
        {"name": "纯蓝幻乐", "part_id": 0},
        tmp_path,
        detail=_reward_detail(),
        resource_types="collect_reward",
    )

    root = tmp_path / "纯蓝幻乐" / "奖励素材"
    assert len(results) == len(calls) == 10
    assert all(result.path.parent == root for result in results)
    assert all(path.parent == root for _, path in calls)
    assert "https://cdn.example.com/collection-cover.jpg" not in [url for url, _ in calls]
