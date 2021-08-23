# coding=utf-8
import Levenshtein
from kie.corrector.reg_match import match
from kie.corrector.fuzzy_correct import FuzzyCorrector

__all__ = ["single_correct", "multi_correct"]

fc = FuzzyCorrector()


def single_correct(source, category="item", threshold=0.7):
    """
    source 只属于一个类别时的纠错
    :param source: 待纠错的字符串
    :param category: 待纠错字符串的属性
    :param threshold: 阈值，在 category == "item" 时才会使用
    :return: 纠错后的结果，结果下标范围（左闭右开），可能出现的单位（category为"result"或"range"时使用）
    """
    assert isinstance(source, str), "the param source must be type of str."
    assert category in {"item", "abbreviation", "result", "unit", "range", "other"}, "unsupported category."
    assert isinstance(threshold, float), "the param threshold must be type of float."

    source = source.replace(" ", "")
    if category == "item":
        target = correct_item(source, threshold)
        return target, get_item_span(source, target), None
    elif category == "abbreviation":
        tmp = source
        tmp = tmp.lstrip("0123456789(（[{<【《")
        l_idx = len(source)-len(tmp)
        tmp = tmp.rstrip("0123456789)）]}>】》")
        r_idx = l_idx + len(tmp)
        return tmp, (l_idx, r_idx), None
    elif category == "unit":
        unit, span = match(source, category)
        if unit is not None:
            return unit, span, None
        return source, (0, len(source)), None
    elif category == "result" or category == "range":
        # 结果和范围中可能包含单位，先正则匹配出单位
        unit, span = match(source, "unit")
        if span is not None:
            left, right = source[:span[0]], source[span[1]:]
            if len(left) >= len(right):
                ret, sub_span = match(left, category)
                if ret is None:
                    return left, (0, span[1]), unit
                else:
                    return ret, (sub_span[0], span[1]), unit
            else:
                ret, sub_span = match(right, category)
                if ret is None:
                    return right, (span[0], len(source)), unit
                else:
                    return ret, (span[0], span[1]+sub_span[1]), unit
        else:
            ret, sub_span = match(source, category)
            if ret is not None:
                return ret, sub_span, None
            else:
                return source, (0, len(source)), None
    elif category == "other":
        return source, (0, len(source)), None


def multi_correct(source, categories, threshold=0.7):
    """
    source 属于多个类别时的拆分与纠错
    :param source: 待拆分纠错的字符串
    :param categories: source 所属的类别数组
    :param threshold: 阈值，在 categories 中包含 "item" 时才会使用
    :return: 拆分并纠错后的列表，列表长度 = len(categories)；无法拆分时，结果列表中对应位置均为 source
    """
    assert isinstance(source, str), "the param source must be type of str."
    assert isinstance(categories, list), "the param categories must be type of list."

    source = source.replace(" ", "")
    if len(categories) == 0:
        return []
    if len(categories) == 1:
        res, _, _ = single_correct(source, categories[0], threshold)
        return [res]
    ret = [source]*len(categories)
    idx, category = 0, ""
    if "unit" in categories:
        idx = categories.index("unit")
        category = "unit"
    elif "item" in categories:
        idx = categories.index("item")
        category = "item"
    elif "range" in categories:
        idx = categories.index("range")
        category = "range"
    elif "result" in categories:
        idx = categories.index("result")
        category = "result"

    if category != "":
        res, span, _ = single_correct(source, category, threshold)
        ret = [res]
        l_categories = categories[:idx]
        r_categories = categories[idx + 1:]
        if len(res) == len(source):
            left, right = source, source
        else:
            left, right = source[:span[0]], source[span[1]:]
        ret = multi_correct(left, l_categories, threshold) + ret
        ret += multi_correct(right, r_categories, threshold)
    return ret


def correct_item(source, threshold=0.7):
    # 首先去掉 source 前后可能存在的单位、数字，并剔除括号中的内容
    _, span = match(source, "unit")
    if span is not None:
        if span[0] >= len(source) - span[1]:
            source = source[:span[0]]
        else:
            source = source[span[1]:]
    source = source.strip("0123456789.。,，!！")
    # 去掉 source 左侧的括号及内容
    right_brackets = ")）]】}>》"
    for bra in right_brackets:
        idx = source.find(bra, 0, int(len(source)*2/3))
        if idx > 0:
            source = source[idx+1:]
            break
    # 去掉 source 右侧的括号及内容
    left_brackets = "(（[【{<《"
    for bra in left_brackets:
        idx = source.find(bra, int(len(source)/3), len(source))
        if idx > 0:
            source = source[:idx]
            break
    # brackets = "(（[【{<《)）]】}>》"
    # for bra in brackets:
    #     idx = source.find(bra)
    #     if idx > 0:
    #         source = source[:idx]
    #         break
    candi = fc.get_top_candidates([source], 1)
    if candi is not None and len(candi) > 0 and len(candi[0]) > 0:
        item, score = candi[0][0]
        # print("score=%f" % score)
        if score > threshold:
            return item
    return source


def get_item_span(source, target):
    ops = Levenshtein.editops(source, target)
    # 1. 左右两边均有delete   2. 左边delete    3. 右边delete
    start, end = 0, len(source)
    single_side = False
    for i, op in enumerate(ops):
        if op[0] != "delete":
            start = op[1]
            break
        if i == len(ops)-1:
            single_side = True
    # 单边删除情况
    if single_side:
        if ops[0][1] == 0:
            return ops[-1][1]+1, end
        else:
            return 0, ops[0][1]
    i = len(ops)-1
    while i >= 0:
        if ops[i][0] == "delete":
            end = ops[i][1]
            i -= 1
        else:
            break
    return start, end


if __name__ == "__main__":
    items = ["12申该细胞绝对值（镜检）1.3umol/L", "杭HBS抗体", "RDW-SD红细胞平均宽度", "百细胞",
             "红细胞平均宽度RDW-SD"]
    for item in items:
        res = single_correct(item, "item")
        print("item correct: [%s] -> %s" % (item, res))
    ranges = ["26.0~ 33.0 pg", "0.5 -- 5.0 %", "11.6-14.8", "0--7", "<1.00X102", "1.23 × 103"]
    for ran in ranges:
        res = single_correct(ran, "range")
        print("range correct: [%s] -> %s" % (ran, res))
    results = ["3.28X104", "4.193", "-12", "23", "0.123", "-32.6", "-2++",
               "12--", "> 1.23x 106", "> -1.23x 106", "<0.05", ">1", "3+", "阴性", "正常"]
    for result in results:
        res = single_correct(result, "result")
        print("result correct: [%s] -> %s" % (result, res))
    multis = [("总二氧化碳（TCO2）", ["item", "abbreviation"]),
              ("RDW-SD红细胞平均宽度", ["abbreviation", "item"]),
              ("乙肝表面抗原>250.00IU/mL", ["item", "result", "unit"]),
              ("乙肝病毒e抗原1226.86t", ["item", "result"]),
              ("0.00~1.00化学发光法", ["range", "other"]),
              ("mIU/m10.00~10.00化学发光法", ["unit", "range", "other"]),
              ("307→100~300 109/L", ["result", "range", "unit"]),
              ("5120-11550U/L", ["range", "unit"]),
              ("RH(D)RH血型", ["abbreviation", "item"]),
              ("122.010.0~160.（g/L", ["result", "range", "unit"])]

    for multi in multis:
        res = multi_correct(multi[0], multi[1])
        print("multi correct: [%s] -> %s" % (multi[0], res))
