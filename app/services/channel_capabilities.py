"""Capabilities for the six-channel workspace; availability is not app entitlement."""
CHANNELS = {
    'linkedin': dict(name='LinkedIn', market='International', mode='EXISTING_API', manage='/linkedin'),
    'facebook': dict(name='Facebook', market='International', mode='EXISTING_API', manage='/meta'),
    'instagram': dict(name='Instagram', market='International', mode='EXISTING_API', manage='/meta'),
    'tiktok': dict(name='TikTok', market='International', mode='MANUAL_HANDOFF', manage='/tiktok',
        blocker='Basic-profile OAuth is available when configured; Direct Post remains disabled and requires separate eligibility review.',
        official_api='Login Kit and Content Posting API', binding='APP_CONFIGURATION_REQUIRED',
        publish_support='NOT_ELIGIBLE_FOR_CURRENT_INTERNAL_USE', scopes=['user.info.basic'],
        publish_scopes=['video.publish'], draft_scopes=['video.upload'],
        docs='https://developers.tiktok.com/docs/en/content-sharing-guidelines'),
    'xiaohongshu': dict(name='小红书 / RED', market='China', mode='MANUAL_HANDOFF',
        blocker='Official account OAuth exists; general organic note publishing entitlement and application onboarding are not verified.',
        official_api='Account OAuth; organic note publishing not verified', binding='APP_ELIGIBILITY_UNVERIFIED',
        publish_support='NOT_VERIFIED_FOR_THIS_APP', scopes=['basic_info'], publish_scopes=[],
        docs='https://openaccount.xiaohongshu.com/docs/api-reference'),
    'douyin': dict(name='抖音 / Douyin', market='China', mode='MANUAL_HANDOFF',
        blocker='Formal website app and approved capability required: 控制台 → 应用详情 → 能力管理 → 能力实验室 → 代替用户发布内容到抖音. Eligibility not verified.',
        official_api='OAuth and approved delegated publishing', binding='APP_REVIEW_REQUIRED',
        publish_support='CONDITIONAL_NOT_ENABLED', scopes=['user_info'], publish_scopes=['video.create.bind'],
        docs='https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/video-management/douyin/create-video/video-create'),
}
NEW_CHANNELS = frozenset({'tiktok', 'xiaohongshu', 'douyin'})
