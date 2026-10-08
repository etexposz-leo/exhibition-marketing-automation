"""Editorial destination catalog, not a claim of provider connectivity.

Keep this separate from the transport registry: adding a card must never enable
an adapter, reuse another platform's token, or silently turn a preview into a job.
"""
from copy import deepcopy


def destination(name, region, media, action, docs, *, manage=None, implemented=False):
    return dict(name=name, region=region, media_requirement=media,
                owner_action=action, docs=docs, manage=manage,
                transport_status='IMPLEMENTED' if implemented else 'NOT_IMPLEMENTED',
                entitlement_status='NOT_VERIFIED', real_enabled=False)


CATALOG = {
    'facebook': destination('Facebook', 'international', 'optional', '选择已授权的 Facebook Page；个人主页不是 Page 发布目标。', 'https://developers.facebook.com/docs/pages-api/posts/', manage='/meta', implemented=True),
    'linkedin': destination('LinkedIn', 'international', 'optional', '确认具体个人或组织账号及发布权限；个人授权不等于公司主页权限。', 'https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/share-on-linkedin', manage='/linkedin', implemented=True),
    'instagram': destination('Instagram', 'international', 'image', '连接受支持的专业账号，并准备符合当前图片适配器的素材。', 'https://developers.facebook.com/docs/instagram-platform/content-publishing/', manage='/meta', implemented=True),
    'tiktok': destination('TikTok', 'international', 'image_or_video', '内部团队自用直发工具不符合当前 Direct Post 用途规则；不能以已有账号代替应用审核。', 'https://developers.tiktok.com/docs/en/content-sharing-guidelines'),
    'youtube': destination('YouTube', 'international', 'video', '需要 Google 开发者项目、YouTube 授权和上传权限；未审核项目可能仅限私密视频。', 'https://developers.google.com/youtube/v3/docs/videos/insert'),
    'pinterest': destination('Pinterest', 'international', 'image_or_video', '需要开发者应用权限、账号授权和明确的 Board。', 'https://developer.pinterest.com/docs/work-with-organic-content-and-users/create-boards-and-pins/'),
    'vimeo': destination('Vimeo', 'international', 'video', '需要应用上传权限与账号授权，随后实现上传及转码状态查询。', 'https://developer.vimeo.com/api/upload/videos'),
    'reddit': destination('Reddit', 'international', 'optional', '需要 Reddit API 使用批准、账号授权，以及目标社区允许的发帖规则。', 'https://support.reddithelp.com/hc/en-us/articles/16160319875092-Reddit-Data-API-Wiki'),
    'x': destination('X', 'international', 'optional', '需要具有发帖访问权限的开发者应用及账号授权。', 'https://docs.x.com/x-api/posts/create-post'),
    'google_business': destination('Google Business Profile', 'international', 'optional', '需要 Business Profile API 访问权限、账号授权和明确的商家地点。', 'https://developers.google.com/my-business/content/posts-data'),
    'xiaohongshu': destination('小红书 / RED', 'china', 'image_or_video', '普通笔记发布 API 对本应用的权限未核实；账号登录不代表具备自动发布接口。', 'https://openaccount.xiaohongshu.com/docs/api-reference', manage='/channels'),
    'douyin': destination('抖音', 'china', 'video', '在开放平台申请代替用户发布内容能力 video.create.bind，再完成账号授权。', 'https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/video-management/douyin/create-video/video-create', manage='/channels'),
    'kuaishou': destination('快手', 'china', 'video', '申请视频发布能力并授权账号；上传成功后仍须查询最终发布状态。', 'https://open.kuaishou.com/platformDocs/openAbility/contentManagement/createAVideo'),
    'wechat_channels': destination('微信视频号', 'china', 'video', '普通视频自动发布接口与本账号资质待核实；不能使用公众号凭据代替。', 'https://developers.weixin.qq.com/'),
    'wechat_official': destination('微信公众号', 'china', 'article', '核实公众号类型、认证和发表接口权限；草稿、发表与群发是不同操作。', 'https://developers.weixin.qq.com/doc/offiaccount/Publish/Publish.html'),
    'weibo': destination('微博', 'china', 'optional', '核实开放平台应用发布权限及当前接口要求，再授权账号。', 'https://open.weibo.com/'),
    'bilibili': destination('哔哩哔哩 / B站', 'china', 'video', '完成开放平台身份及应用审核，申请稿件分发权限并授权 UP 主。', 'https://open.bilibili.com/doc/main'),
    'zhihu': destination('知乎', 'china', 'article', '适用于本应用的文章发布接口与合作资质尚未核实。', 'https://www.zhihu.com/'),
    'toutiao': destination('今日头条', 'china', 'article_or_video', '核实头条号内容发布合作接口与账号资质。', 'https://mp.toutiao.com/'),
    'baijiahao': destination('百家号', 'china', 'article_or_video', '核实百家号内容发布接口、应用接入及账号权限。', 'https://baijiahao.baidu.com/'),
    'huoshan': destination('火山（暂按抖音火山版）', 'china', 'video', '确认产品名称；独立发布接口未核实，不复用抖音授权或向抖音重复发布。', 'https://www.huoshan.com/'),
}


def catalog():
    return [dict(id=key, **deepcopy(value)) for key, value in CATALOG.items()]
