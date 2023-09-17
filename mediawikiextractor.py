import regex as re
import json
import argparse
import requests
import sys
import datetime
import time
from convert_wiki_text import convert


def devide_list(input_list, chunk_size):
    """
    将列表拆分为指定长度的子列表。

    参数：
    input_list: 要拆分的列表。
    chunk_size: 子列表的长度。

    返回值：
    包含子列表的列表。
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size必须大于0")

    return [input_list[i:i + chunk_size] for i in range(0, len(input_list), chunk_size)]


def get_config():
    try:
        with open(config_path, 'r', encoding='UTF-8') as file:
            config_data = json.load(file)
        pageid_list = config_data.get("page_ids")
        api_url = config_data.get("api")
        source = config_data.get("source")
        categories = config_data.get("categories")
        exclude_ids = config_data.get("exclude_ids")
        exclude_categories = config_data.get("exclude_categories")
        cleaning_rule = config_data.get("cleaning_rule")
        exclude_titles = config_data.get("exclude_titles")
    except FileNotFoundError:
        print(f"配置文件 '{config_path}' 未找到")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"配置文件 '{config_path}' 解析失败")
        sys.exit(1)
    except BaseException:
        print(f"读取配置文件 '{config_path}' 时出现未知错误")
        sys.exit(1)

    return pageid_list, api_url, source, categories, exclude_ids, exclude_categories, cleaning_rule, exclude_titles


def get_page_ids(api_url, category):
    # 设置请求参数
    params = {
        'action': 'query',
        'format': 'json',
        'list': 'categorymembers',
        'cmtitle': f'Category:{category}',
        'cmlimit': 500
    }

    page_ids = []

    # 循环请求，直到获取全部页面
    while True:
        while True:
            try:
                # 发送get请求，获取响应
                response = requests.get(api_url, params=params, timeout=100)
                # 检查响应状态码是否正确
                response.raise_for_status()
                # 解析响应内容
                data = response.json()

            except requests.exceptions.RequestException as e:
                # 打印错误信息
                print(f"请求错误:{e},十秒后重试")
                # 等待10秒
                time.sleep(10)
                print("重试")
            else:
                break

        # 遍历查询结果
        for item in data['query']['categorymembers']:
            # 将查询结果添加到page_ids列表中
            page_ids.append(item['pageid'])

        # 如果查询结果中有continue字段，则获取continue字段的值
        if 'continue' in data:
            # 获取continue字段的值
            params['cmcontinue'] = data['continue']['cmcontinue']
        else:
            # 否则，跳出循环
            break

    # 返回page_ids列表
    return page_ids


def get_page(pageid_list, api_url, source, cleaning_rule, exclude_titles):
    '''
    获取页面内容
    :param pageid_list: 页面id列表
    :param api_url: api请求地址
    :param source: 来源
    :param cleaning_rule: 去除规则
    :param exclude_titles: 不需要的标题
    :return:
    '''
    params = {'action': 'query', 'format': 'json', 'prop': 'cirrusdoc', 'curtimestamp': 1, 'indexpageids': 1}
    data = []
    for pageidlist_devide in devide_list(pageid_list, 50):
        param_pageids = '|'.join(map(str, pageidlist_devide))
        params = {**params, **{'pageids': param_pageids}}
        request_times = 0
        while True:
            try:
                # 发送GET请求获取页面内容
                requests_return = requests.get(api_url, params=params, timeout=(10, 30))
                request_times = request_times + 1
            except BaseException as e:
                print(f"[error]请求获取页面内容失败，正在重试。请求的api:{api_url}，请求的参数{params}，错误:{e},十秒后重试")
                # 等待10秒
                time.sleep(10)
                print("重试")
            else:
                if requests_return.ok:
                    requests_return: dict = requests_return.json()
                    if 'batchcomplete' in requests_return:
                        print(f"第{request_times}次请求，请求页面数量:{len(pageidlist_devide)}个。")
                        break
                    else:
                        print("[error]响应不完整，可能因请求页面数据量过大而导致。请尝试调整请求的数据量。")
        for pageid in pageidlist_devide:
            result = process_cirrusdoc(pageid, requests_return, cleaning_rule, exclude_titles)
            if not result:
                break
            else:
                p_cirrusdoc, title, version, timestamp, cirrusdoc = result
            data.extend([{"title": title, "pageid": pageid, "version": version, "timestamp": timestamp, "source": source, "text": p_cirrusdoc, "cirrusdoc": cirrusdoc}])
            with open(output_path, 'w', encoding='UTF-8') as output_file:
                json.dump(data, output_file, ensure_ascii=False, indent=4)


def process_cirrusdoc(pageid, requests_return, cleaning_rule, exclude_titles):
    # 获取页面json
    rawpagejson = requests_return['query']['pages'][str(pageid)]
    # 获取页面标题
    title = rawpagejson['title']
    # 获取页面更新时间
    timestamp = rawpagejson['cirrusdoc'][0]['source']['timestamp']
    # 获取页面版本
    version = rawpagejson['cirrusdoc'][0]['source']['version']
    # 获取页面中的标题
    headings = rawpagejson['cirrusdoc'][0]['source']['heading']
    # 获取页面文本
    cirrusdoc = rawpagejson['cirrusdoc'][0]['source']['text']
    # 使用re模块的search函数来查找匹配
    for exclude_title in exclude_titles:
        match = re.search(exclude_title, title)  # 排除标题
        # 如果找到匹配，则match对象不为None
        if match:
            print(f"排除标题：{title}")
            return

    # 打印当前处理
    print(f"当前处理：[标题]{title}[页面id]{pageid}[最后修改]{timestamp}[版本]{version},")
    # 获取原页面文本
    source_text = rawpagejson['cirrusdoc'][0]['source']['source_text']
    # 处理原页面文本
    source_text_p = preprocess_source_text(source_text)

    # 将页面中的标题转换为正则表达式
    headings_pattern = '|'.join(re.escape(heading) for heading in headings)
    headings_pattern1 = f"\n*=+(?: )*(?:{headings_pattern})(?: )*=+\n*"
    matching_headings1 = re.findall(headings_pattern1, source_text_p)  # 获取所有带=的标题
    matching_headings2 = findall('[^\n}}{{><=]*', headings_pattern1, '(?!=+)[^\n}}{{><]*', source_text_p)  # 获取所有带=的标题与上下文

    # 恢复原标题
    cirrusdoc2 = cirrusdoc
    # 判断带=的标题是否与带=的标题与上下文数量匹配
    if len(matching_headings1) == len(matching_headings2):
        n = 0
        while n < len(matching_headings1):
            # 替换带=的标题为正则表达式
            pattern = re.escape(re.sub(headings_pattern1, r'_space_placeholder___', matching_headings2[n]))
            pattern = re.sub(r"_space_placeholder___", r'(?: +|(?P<equal_sign>=+))', pattern)
            # 判断带=的标题与上下文是否有上下文
            if pattern == "(?: +|(?P<equal_sign>=+))":
                print(f"页面\"{title}\"中的标题：{repr(matching_headings2[n])}无法匹配")
            else:
                # 替换带=的标题为正则表达式
                cirrusdoc2 = re.sub(pattern, rf'\g<equal_sign>{matching_headings2[n]}', cirrusdoc2)

            n = n + 1

    # 恢复原换行符
    print('恢复原换行符', end="\r")
    cirrusdoc3 = cirrusdoc2
    matching_newline = findall('[^\n}}{{><]+', '\n+', '[^\n}}{{><]+', source_text_p)  # 获取所有'\n'的上下文
    n = 0
    while n < len(matching_newline):
        pattern = re.sub(r"\n+", r'( +)', escape(matching_newline[n]))
        if pattern != "( +)":
            cirrusdoc3 = re.sub(pattern, rf'{matching_newline[n]}', cirrusdoc3)
        n = n + 1

    # 清理cirrusdoc3
    print('开始清理', end="\r")
    cirrusdoc4 = clear_text(cirrusdoc3, source_text, source_text_p, cleaning_rule)
    return cirrusdoc4, title, version, timestamp, cirrusdoc


def clear_text(cirrusdoc, source_text, source_text_p, cleaning_rule):
    """
    清理cirrusdoc

    参数：
    cirrusdoc：需要清理的字符串
    source_text：原始字符串

    返回值：
    清理后的字符串
    """
    # 1.清理图片

    c_source_text = re.sub(r"<big>|</big>|<small>|</small>|'''''|'''|''|<br />|<br/>|<br[^>]*>|<del[^>]*>|</del>|<s[^>]*>|</s>|<span[^>]*>|</span>|<ins[^>]*>|</ins>|<u[^>]*>|</u>|<poem[^>]*>|</poem>|<div[^>]*>|</div>", "", source_text)
    c1_source_text = re.sub(r'\{\{[Ll]ang\|[jekfr][ranou]\|((?:[^}{]|\n)+)\}\}', r'\1', c_source_text)  # 匹配[Ll]ang|[jekfr][ranou]|
    c2_source_text = re.sub(r'\[\[([^\]]*)\]\]', r'\1', c1_source_text)
    c3_source_text = re.sub(r'\[https?://[^}{\]\[ ]+ ([^\]\[]+)\]', r'\1', c1_source_text)
    print('清理图片', end="\r")
    gallery = re.findall('<gallery[^>]*>(?:[^<]|\n)+</gallery>', c2_source_text)

    for i in gallery:
        text = re.sub(r'<gallery[^>]*>(?:\n)*((?:[^<]|\n)+?)(?:\n)*</gallery>', r'\1', i)
        text = re.sub(r'(?:File:|文件:|[Ii]mage:)*[^\|\n]+\|', r'', text)
        pattern = re.sub(r'\n+', r'( +)', text)
        cirrusdoc = re.sub(pattern, r"", cirrusdoc)

    print('清理注释', end="\r")
    # 2.清理注释
    ref = re.findall('<ref[^>]*>(?:[^<]|\n)+</ref>', c3_source_text)
    for i in ref:
        pattern = re.sub(r'<ref[^>]*>((?:[^<]|\n)+)</ref>', r' *\1 *', i)
        cirrusdoc = re.sub(pattern, r"", cirrusdoc)

    print('清理本站外文字链接', end="\r")
    # 3.清理本站外文字链接
    external_link = re.findall(r'\[https?://[^}{\]\[ ]+ [^\]\[]+\]', source_text_p)
    for i in external_link:
        pattern = re.sub(r'\[https?://[^}{\]\[ ]+ ([^\]\[]+)\]', r'\1', i)
        link = re.sub(r'\[(https?://[^}{\]\[ ]+) ([^\]\[]+)\]', r'\1', i)
        cirrusdoc = re.sub(f"{re.escape(pattern)}(?!.*{re.escape(pattern)})", rf"{pattern}:{link}", cirrusdoc)

    # 4.自定义清理
    print('自定义清理', end="\r")
    for pattern in cleaning_rule:
        cirrusdoc = re.sub(pattern, r"", cirrusdoc)

    return cirrusdoc


def findall(pattern1, pattern2, pattern3, text):
    """
    匹配所有pattern1+pattern2+pattern3

    参数：
    pattern1: 开头可与上一次匹配重叠正表达式
    pattern2: 不重叠匹配的正表达式
    pattern3：末尾可与上一次匹配重叠的正表达式

    返回值：
    包含所有匹配项的列表。
    """
    # 定义一个空列表，用于存放匹配结果
    matchs = []
    # 将pattern2和pattern3拼接成一个pattern
    pattern = f"{pattern2}{pattern3}"
    # 使用re模块的findall方法，查找text中匹配pattern的所有结果
    match1 = re.findall(pattern, text)
    # 定义变量n，用于记录匹配结果的数量
    n = 0
    # 循环遍历match1中的每一个结果
    while n < len(match1):
        # 将pattern1和match1中第n个结果拼接成一个字符串
        pattern = f"{pattern1}{re.escape(match1[n])}"
        # 使用re模块的findall方法，查找text中匹配pattern的所有结果
        match2 = re.findall(pattern, text)
        # 定义变量nn，用于记录匹配结果的数量
        nn = 0
        # 循环遍历match2中的每一个结果
        while nn < len(match2):
            # 将match2中第nn个结果添加到matchs列表中
            matchs.append(match2[nn])
            # 将nn加1
            nn = nn + 1

        # 将n加1
        n = n + 1

    # 返回matchs列表
    return matchs


def preprocess_source_text(source_text):
    # 简繁转换
    source_text = convert(source_text)
    # 转换部分基本模板
    source_text = re.sub(r"\{\{(?:Zh|Zh-hans|Zh-hant|Ja icon|Ja|En|Ko|Ru|Fr|De)\}\}|\{\{Languageicon[^}{]*\}\}|\{\{clear\}\}|\{\{剧透\}\}|\{\{剧透提醒\}\}|<big>|</big>|<small>|</small>|'''''|'''|''|<br />|<br/>|<br[^>]*>|<del[^>]*>|</del>|<s[^>]*>|</s>|<span[^>]*>|</span>|<ins[^>]*>|</ins>|<u[^>]*>|</u>|<poem[^>]*>|</poem>|<div[^>]*>|</div>|\[\[File:[^\]\[]*\]\]|\[\[文件:[^\]\[]*\]\]|\[\[[Ii]mage:[^\]\[]*\]\]|\{\{#tag:div\|<img[^}{]*\}\}|\{\{#ifexpr.*\n.*\n.*\}\}\}\}", r'', source_text)  # 匹配并删除  #|<code>|</code>|<nowiki>|</nowiki>|<pre>|</pre>
    source_text = re.sub(r'\[\[(?!File:)(?!文件:)(?![Ii]mage:)(?!#)[^[}{\]|]*\|(?!\*)([^}{[\]]*)\]\]', r'\1', source_text)  # 匹配[[实际页面|显示文字]]]
    source_text = re.sub(r'\{\{[Rr]uby\|([^|}{]+)\|([^|}{]+)[|jaenzh]*\}\}', r'\1', source_text)  # 匹配[Rr]uby
    source_text = re.sub(r'\[\[(?!File:)(?!文件:)(?![Ii]mage:)(?!#)[^[}{\]|]*\|(?!\*)([^}{[\]]*)\]\]', r'\1', source_text)  # 匹配[[实际页面|显示文字]]] for {{lang|ja|「[[致永远之星|{{ruby|永遠|とわ}}の星へ]]」}}
    source_text = re.sub(r'\{\{[Ff]ont[^}{]*\|((?:[^}{]|\n)+)\}\}', r'\1', source_text)  # 匹配[Ff]ont
    source_text = re.sub(r'\{\{[Ll]j\|((?:[^}{]|\n)+)\}\}', r'\1', source_text)  # 匹配[Ll]j
    source_text = re.sub(r'\{\{[Cc]olor\|[^|}{]+\|((?:[^}{]+)|\n)\}\}', r'\1', source_text)  # 匹配color
    source_text = re.sub(r'\{\{coloredlink\|[^|}{]+\|([^}{]+)\}\}', r'\1', source_text)  # 匹配coloredlink
    source_text = re.sub(r'\{\{[Ll]ang-ja\|([^}{|]+)\|([^}{|]+)\}\}', r'日语：\1', source_text)  # {{lang-ja|'''まどひ白きの神隠し'''|ja}}
    source_text = re.sub(r'\{\{[Ll]ang-de\|([^}{]+)\}\}', r'德语：\1', source_text)  # 匹配
    source_text = re.sub(r'\{\{[Ll]ang-en\|([^}{]+)\}\}', r'英语：\1', source_text)  # 匹配
    source_text = re.sub(r'\{\{[Ll]ang-fr\|([^}{]+)\}\}', r'法语：\1', source_text)  # 匹配
    source_text = re.sub(r'\{\{[Ll]ang-ja\|([^}{]+)\}\}', r'日语：\1', source_text)  # 匹配
    source_text = re.sub(r'\{\{[Ll]ang-ko\|([^}{]+)\}\}', r'韩语：\1', source_text)  # 匹配
    source_text = re.sub(r'\{\{[Ll]ang-ru\|([^}{]+)\}\}', r'俄语：\1', source_text)  # 匹配
    source_text = re.sub(r'\{\{[Ll]ang-sa\|([^}{]+)\}\}', r'梵語：\1', source_text)  # 匹配
    source_text = re.sub(r'\{\{[Ll]ang-th\|([^}{]+)\}\}', r'泰語：\1', source_text)  # 匹配
    source_text = re.sub(r'\{\{[Ll]ang-uk\|([^}{]+)\}\}', r'烏克蘭語：\1', source_text)  # 匹配
    source_text = re.sub(r'\{\{[Ll]ang\|[jekfr][ranou]\|((?:[^}{]|\n)+)\}\}', r'\1', source_text)  # 匹配[Ll]ang|[jekfr][ranou]|
    source_text = re.sub(r'\{\{黑幕\|([^}{|]+)\}\}', r'\1', source_text)  # 黑幕1
    source_text = re.sub(r'\{\{黑幕\|([^}{|]+)\|[^}{|]+\}\}', r'\1', source_text)  # 黑幕2
    source_text = re.sub(r'\{\{(?:胡话|JK|jk)\|(?:1=)*([^}{|]+)(?:\|[^}{|]+)*?\}\}', r'\1', source_text)  # 胡话
    source_text = re.sub(r'\{\{交叉颜色\|c1=#[0-9a-fA-F]{1,9}\|c2=#[0-9a-fA-F]{1,9}\|([^|}{]+)\|([^|}{]+)\|([^|}{]+)\}\}', r'\1\2\3', source_text)
    source_text = re.sub(r'\{\{交叉颜色\|c1=#[0-9a-fA-F]{1,9}\|c2=#[0-9a-fA-F]{1,9}\|([^|}{]+)\|([^|}{]+)\|([^|}{]+)\|([^|}{]+)\|([^|}{]+)\}\}', r'\1\2\3\4\5', source_text)
    source_text = re.sub(r'\{\{交叉颜色F\|#[0-9a-fA-F]{1,9},#[0-9a-fA-F]{1,9},#[0-9a-fA-F]{1,9}\|([^|}{]+)\}\}', r'\1', source_text)
    source_text = re.sub(r'\[\[([^\]\[]*)\]\]', r'\1', source_text)
    source_text = re.sub(r"\[\[File:[^\]\[]*\]\]|\[\[文件:[^\]\[]*\]\]|\[\[[Ii]mage:[^\]\[]*\]\]", r'', source_text)  # 匹配并删除
    source_text = '\n'.join([line.lstrip('*') for line in source_text.split('\n')])  # 删除所有行首的'*'
    return source_text


def escape(text):
    characters_to_escape = [')', '(', ']', '[', '|', '*', '+', '?']
    escaped_text = text
    for char in characters_to_escape:
        escaped_text = escaped_text.replace(char, '\\' + char)
    return escaped_text


def escape_s(text):
    characters_to_escape = [']', '[', '|', '*', '+', '?']
    escaped_text = text
    for char in characters_to_escape:
        escaped_text = escaped_text.replace(char, '\\' + char)
    return escaped_text


def main():
    '''
    主函数，用于获取页面id，并获取页面信息
    '''
    current_time = datetime.datetime.now()
    print("mediawikiextractor\n运行开始于：", current_time)
    pageid_list, api_url, source, categories, exclude_ids, exclude_categories, cleaning_rule, exclude_titles = get_config()
    if categories:
        for category in categories:
            print(f"正在获取分类{category}中的所有页面id" + " " * 30, end="\r")
            # 获取指定Category的页面id
            page_ids = get_page_ids(api_url, category)
            # 将获取到的页面id添加到pageid_list中
            pageid_list.extend(page_ids)
            time.sleep(1)  # 设置睡眠时间，防止被wikimedia服务器封禁IP
    else:
        print("未设置要获取的Category，跳过获取categories中的页面id")
    if exclude_categories:
        for exclude_category in exclude_categories:
            print(f"正在获取分类{exclude_category}中的所有页面id" + " " * 30, end="\r")
            # 调用get_page_ids函数，获取exclude_category中的页面id
            page_ids = get_page_ids(api_url, exclude_category)
            # 将获取的页面id添加到exclude_ids中
            exclude_ids.extend(page_ids)
            time.sleep(1)  # 设置睡眠时间，防止被wikimedia服务器封禁IP
    else:
        # 如果exclude_categories中没有元素，则输出提示信息
        print("未设置要排除的Category，跳过获取exclude_categories中的页面id")
    if exclude_ids:
        # 如果exclude_ids存在，则删除pageid_list中存在于exclude_ids的元素
        pageid_list = [x for x in pageid_list if x not in exclude_ids]
    if not pageid_list:
        # 如果pageid_list为空，则打印提示信息并退出程序
        print("没有需要处理的页面id，程序结束")
        sys.exit(1)
    pageid_list = sorted(list(set(pageid_list)))
    get_page(pageid_list, api_url, source, cleaning_rule, exclude_titles)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='')
    parser.add_argument('--config', required=True, help='Path to config file')
    parser.add_argument('--output', required=True, help='Path to output file')
    args = parser.parse_args()
    config_path = args.config
    output_path = args.output
    main()
