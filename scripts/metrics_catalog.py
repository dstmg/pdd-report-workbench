"""Source field catalog. Unknown aggregation rules remain source-only."""
from decimal import Decimal,InvalidOperation

META = {'日期','商品ID','商品名称','推广场景','推广名称','出价方式','分组','是否已删除',
        '推广方案','场次名称','直播场次起止时间','创意样式','创意图片','品牌词包'}
ALIASES = {'总花费(元)':'spend','花费(元)':'spend','成交花费(元)':'conversionSpend',
           '交易额(元)':'revenue','净交易额(元)':'netRevenue','成交笔数':'orders',
           '曝光量':'impressions','点击量':'clicks','实际投产比':'roi','投入产出比':'roi'}
ADDITIVE = {'总花费(元)','花费(元)','成交花费(元)','交易额(元)','净交易额(元)','净成交笔数',
            '结算交易额(元)','结算成交笔数','成交笔数','直接交易额(元)','间接交易额(元)',
            '直接成交笔数','间接成交笔数','曝光量','点击量','询单花费(元)','询单量','收藏花费(元)',
            '收藏量','关注花费(元)','关注量','店铺关注量','深度观看','关注目标增量','关注目标花费(元)',
            '深度观看目标增量','深度观看目标花费(元)','直播评论量','商品收藏量'}
RATIOS = {
    '实际投产比':('交易额(元)','成交花费(元)',1), '投入产出比':('交易额(元)','花费(元)',1),
    '净实际投产比':('净交易额(元)','成交花费(元)',1), '结算投产比':('结算交易额(元)','成交花费(元)',1),
    '每笔净成交花费(元)':('成交花费(元)','净成交笔数',1),
    '净交易额占比':('净交易额(元)','交易额(元)',100), '净成交笔数占比':('净成交笔数','成交笔数',100),
    '每笔净成交金额(元)':('净交易额(元)','净成交笔数',1),
    '每笔结算成交花费(元)':('成交花费(元)','结算成交笔数',1),
    '交易额结算率':('结算交易额(元)','交易额(元)',100), '订单结算率':('结算成交笔数','成交笔数',100),
    '每笔结算成交金额(元)':('结算交易额(元)','结算成交笔数',1),
    '每笔成交花费(元)':('成交花费(元)','成交笔数',1), '每笔成交金额(元)':('交易额(元)','成交笔数',1),
    '平均询单成本(元)':('询单花费(元)','询单量',1), '平均收藏成本(元)':('收藏花费(元)','收藏量',1),
    '平均关注成本(元)':('关注花费(元)','关注量',1), '平均关注成本':('关注目标花费(元)','关注目标增量',1),
    '平均深度观看成本':('深度观看目标花费(元)','深度观看目标增量',1),
    '千次曝光花费(元)':('总花费(元)','曝光量',1000), '千次曝光转化数':('成交笔数','曝光量',1000),
    '千次曝光交易额(元)':('交易额(元)','曝光量',1000), '千次曝光增粉数':('关注量','曝光量',1000)}


def numeric(value):
    if value is None or str(value).strip() in ('','-','--'):
        return None
    try:result=Decimal(str(value).replace(',','').replace('%',''))
    except InvalidOperation as exc:raise ValueError('源字段不是有效数字，请核对报表格式') from exc
    if not result.is_finite():raise ValueError('源字段包含非有限数值')
    return float(result)


def catalog(headers):
    result=[]
    for name in dict.fromkeys(headers):
        if name in META:
            continue
        ratio = RATIOS.get(name)
        if name=='每笔成交花费(元)' and '成交花费(元)' not in headers:
            ratio=('花费(元)','成交笔数',1)
        if name=='千次曝光花费(元)' and '总花费(元)' not in headers:
            ratio=('花费(元)','曝光量',1000)
        kind='sum' if name in ADDITIVE else 'ratio' if ratio else 'source'
        group = '净成交与结算' if any(w in name for w in ('净','结算','豁免')) else '互动与转化' if any(w in name for w in ('询单','收藏','关注','观看','评论','增粉')) else '流量' if any(w in name for w in ('曝光','点击')) else '成交与花费'
        unit='%' if any(w in name for w in ('率','占比')) else '倍' if '投产' in name or '产出比' in name else '元' if '(元)' in name or '成本' in name else '次'
        result.append({'key':ALIASES.get(name,name),'name':name,'group':group,'kind':kind,
            'unit':unit,'digits':0 if kind=='sum' and unit=='次' else 2,
            'ratio':[ALIASES.get(ratio[0],ratio[0]),ALIASES.get(ratio[1],ratio[1]),ratio[2]] if ratio else None,
            'description':'基础数值加总' if kind=='sum' else '先合计分子和分母，再计算；零分母显示—' if kind=='ratio' else '汇总规则未确认：完整周期使用官方值，其他范围请查看每日原始值'})
    return result


def mapped(row, definitions):
    return {f['key']:numeric(row.get(f['name'])) for f in definitions}
