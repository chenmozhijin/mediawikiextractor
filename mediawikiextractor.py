import regex as re
from bs4 import BeautifulSoup
from markdown import markdown
import json
import argparse
import requests
import sys
import html2text
import datetime
import time


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
        site_url = config_data.get("site_url")
    except FileNotFoundError:
        print(f"配置文件 '{config_path}' 未找到")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"配置文件 '{config_path}' 解析失败")
        sys.exit(1)
    except BaseException:
        print(f"读取配置文件 '{config_path}' 时出现未知错误")
        sys.exit(1)

    return pageid_list, api_url, source, categories, exclude_ids, exclude_categories, cleaning_rule, exclude_titles, site_url


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


def get_page(pageid_list, api_url, source, cleaning_rule, exclude_titles, site_url):
    '''
    获取页面内容
    :param pageid_list: 页面id列表
    :param api_url: api请求地址
    :param source: 来源
    :param cleaning_rule: 去除规则
    :param exclude_titles: 不需要的标题
    :return:
    '''
    params = {'action': 'query', 'format': 'json', 'prop': 'info|revisions', 'curtimestamp': 1, 'indexpageids': 1}
    data = []
    request_times = 0
    for pageidlist_devide in devide_list(pageid_list, 50):
        param_pageids = '|'.join(map(str, pageidlist_devide))
        params1 = {**params, **{'pageids': param_pageids}}
        while True:
            try:
                # 发送GET请求获取页面内容
                requests_return = requests.get(api_url, params=params1, timeout=(10, 30))
                request_times = request_times + 1
            except BaseException as e:
                print(f"[error]请求获取页面信息失败，正在重试。请求的api:{api_url}，请求的参数{params1}，错误:{e},十秒后重试")
                # 等待10秒
                time.sleep(10)
                print("重试")
            else:
                if requests_return.ok:
                    requests_return: dict = requests_return.json()
                    if 'batchcomplete' in requests_return:
                        print(f"第{request_times}次请求，请求页面信息数量:{len(pageidlist_devide)}个。")
                        break
                    else:
                        print("[error]响应不完整，可能因请求页面数据量过大而导致。请尝试调整请求的数据量。")
        for pageid in pageidlist_devide:
            # 获取页面json
            rawpagejson = requests_return['query']['pages'][str(pageid)]
            # 获取页面标题
            title = rawpagejson['title']
            # 获取页面更新时间
            timestamp = rawpagejson['revisions'][0]['timestamp']
            # 获取页面版本
            version = rawpagejson['revisions'][0]['revid']
            # 使用re模块的search函数来查找匹配
            for exclude_title in exclude_titles:
                match = re.search(exclude_title, title)  # 排除标题
                # 如果找到匹配，则match对象不为None
                if match:
                    print(f"排除标题：{title}")
                    break
            params2 = {'curid': pageid}
            while True:
                try:
                    # 发送GET请求获取页面内容
                    response = requests.get(site_url, params=params2, timeout=100)
                    request_times = request_times + 1
                except BaseException as e:
                    print(f"[error]请求获取页面失败，正在重试。请求的url:{api_url}，请求的参数{params2}，错误:{e},十秒后重试")
                    # 等待10秒
                    time.sleep(10)
                    print("重试")
                else:
                    print(f"当前请求&处理:[标题]{title}[页面id]{pageid}[最后修改]{timestamp}[版本]{version}[请求次数]{request_times}")
                    break

            result = process_html(response.text, cleaning_rule)
            data.extend([{"title": title, "pageid": pageid, "version": version, "timestamp": timestamp, "source": source, "text": result}])
            with open(output_path, 'w', encoding='UTF-8') as output_file:
                json.dump(data, output_file, ensure_ascii=False, indent=4)


def process_html(text, cleaning_rule):
    # 使用Beautiful Soup解析HTML内容
    soup = BeautifulSoup(text, 'html.parser')
    # 查找具有特定类名的<div>元素
    div_element = soup.find('div', class_='mw-parser-output')
    # 如果找到了<div>元素，则查找并删除所有<table>元素
    if div_element:
        for i in ["navbox", "noprint"]:
            tables_to_remove = div_element.find_all('table', class_=f"{i}")
            for table in tables_to_remove:
                table.extract()  # 从DOM中移除<table>元素

    h = html2text.HTML2Text()
    # Ignore converting links from HTML
    h.ignore_links = True
    h.ignore_images = True
    # h.ignore_tables = True
    h.ignore_emphasis = True
    Markdown = h.handle(div_element.prettify())
    html = markdown(Markdown)
    text = ''.join(BeautifulSoup(html, features="lxml").findAll(string=True))
    # 自定义清理
    for pattern in cleaning_rule:
        text = re.sub(pattern, r"", text, count=0, flags=re.DOTALL)
    return text


def main():
    '''
    主函数，用于获取页面id，并获取页面信息
    '''
    current_time = datetime.datetime.now()
    print("mediawikiextractor\n运行开始于：", current_time)
    pageid_list, api_url, source, categories, exclude_ids, exclude_categories, cleaning_rule, exclude_titles, site_url = get_config()
    if categories:
        for category in categories:
            print(f"正在获取分类{category}中的所有页面id")
            # 获取指定Category的页面id
            page_ids = get_page_ids(api_url, category)
            # 将获取到的页面id添加到pageid_list中
            pageid_list.extend(page_ids)
            time.sleep(1)  # 设置睡眠时间，防止被wikimedia服务器封禁IP
    else:
        print("未设置要获取的Category，跳过获取categories中的页面id")
    if exclude_categories:
        for exclude_category in exclude_categories:
            print(f"正在获取分类{exclude_category}中的所有页面id")
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
    get_page(pageid_list, api_url, source, cleaning_rule, exclude_titles, site_url)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='')
    parser.add_argument('--config', required=True, help='Path to config file')
    parser.add_argument('--output', required=True, help='Path to output file')
    args = parser.parse_args()
    config_path = args.config
    output_path = args.output
    main()
