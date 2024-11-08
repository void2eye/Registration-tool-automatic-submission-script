import time
import json
import requests
import getpass
from rich.table import Table
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Event, Thread
from utils import get_random_user_agent, clear_screen, console


class EnrollmentSubmitter:
    def __init__(self, enrollment_id, access_token, session, stop_event):
        self.user_extra_info = {}
        self.enrollment_request_data = []
        self.access_token = access_token
        self.enrollment_id = enrollment_id
        self.base_url = 'https://api-xcx-qunsou.weiyoubot.cn/xcx/enroll'
        self.user_info_url = f'{
            self.base_url}/v1/userinfo?access_token={self.access_token}'
        self.request_details_url = f'{
            self.base_url}/v1/req_detail?access_token={self.access_token}&eid={self.enrollment_id}'
        self.submit_url = f'{self.base_url}/v5/enroll'
        self.failed_attempts = 0
        self.failed_attempts_limit = 20
        self.session = session
        self.stop_event = stop_event  # 用于控制线程停止

    def get_headers(self):
        return {'User-Agent': get_random_user_agent()}

    def fetch_user_info(self):
        response = self.session.get(
            self.user_info_url, headers=self.get_headers())
        user_info = response.json()
        for item in user_info['data']['extra_info']:
            names = item['name'] if isinstance(
                item['name'], list) else [item['name']]
            for name in names:
                self.user_extra_info[name] = item['value']
        console.print("\n[green]=== 用户信息已成功获取 ===[/green]")
        for name, value in self.user_extra_info.items():
            console.print(f"  - [yellow]{name}[/yellow]: {value}")
        console.print("\n[green]=== 开始抢讲座 ===[/green]")

    def fetch_enrollment_details(self):
        try:
            response = self.session.get(
                self.request_details_url, headers=self.get_headers())
            enrollment_data = response.json()
        except json.JSONDecodeError:
            console.print(f"{time.strftime('%H:%M:%S')
                             } | [red][!] 获取报名详情失败[/red]")
            return False

        if not enrollment_data['data']['req_info']:
            console.print(f"{time.strftime('%H:%M:%S')
                             } | [yellow][-] 报名尚未开始[/yellow]")
            return False

        for item in enrollment_data['data']['req_info']:
            field_value = self.user_extra_info.get(
                item['field_name'], '1' * item.get('min_length', 11))
            self.enrollment_request_data.append({
                "field_name": item['field_name'],
                "field_value": field_value,
                "field_key": item["field_key"]
            })
        return bool(self.enrollment_request_data)

    def submit_enrollment(self):
        body = {
            "access_token": self.access_token,
            "eid": self.enrollment_id,
            "info": self.enrollment_request_data,
            "on_behalf": 0,
            "items": [],
            "referer": "",
            "fee_type": ""
        }
        response = self.session.post(
            self.submit_url, json=body, headers=self.get_headers()).json()

        if response['sta'] == 0:
            console.print(f"{time.strftime('%H:%M:%S')
                             } | [green][+] 报名已成功提交！[/green]")
            return True

        console.print(f"{time.strftime('%H:%M:%S')
                         } | [red][-] 提交失败，返回信息：{response['msg']}[/red]")
        self.failed_attempts += 1
        return False

    def run(self):
        self.fetch_user_info()
        while self.failed_attempts < self.failed_attempts_limit and not self.stop_event.is_set():
            if self.fetch_enrollment_details():
                if self.submit_enrollment():
                    break
            time.sleep(0.25)
        if self.failed_attempts >= self.failed_attempts_limit:
            console.print("[red][!] 提交失败次数已达到%d次，停止运行。[/red]" %
                          self.failed_attempts_limit)


class TokenRetriever:
    def __init__(self):
        self.base_url = 'https://api-xcx-qunsou.weiyoubot.cn/xcx/enroll'
        self.phone_login_url = f'{self.base_url}/v1/login_by_phone'
        self.user_history_url = f'{
            self.base_url}/v1/user/history?access_token='
        self.session = requests.Session()
        self.stop_event = Event()  # 用于控制线程的停止

    def get_headers(self):
        return {'User-Agent': get_random_user_agent()}

    def login_with_phone(self):
        phone = input("[!] 请输入手机号：")
        password = getpass.getpass("[!] 请输入密码(不显示)：")

        credentials = {"phone": phone, "password": password}
        response = self.session.post(
            self.phone_login_url, json=credentials, headers=self.get_headers()).json()

        if response['sta'] == -1:
            console.print(f"[red][!] 登录失败，{response['msg']}[/red]")
            return None

        clear_screen()
        console.print(f"\n[green]=== 登录成功，身份为 {
                      phone[0:3]}****{phone[-4:]} ===[/green]\n")
        return response['data']['access_token']

    def show_user_history(self, history_data):
        console.print('[!] 请选择要提交的表单序号')
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("序号", style="dim")
        table.add_column("名称", style="bold")
        table.add_column("状态", style="green")

        for idx, entry in enumerate(history_data, 1):
            status_text = '进行中' if entry['status'] == 1 else '未开始'
            table.add_row(str(idx), entry['name'], status_text)

        console.print(table)

    def run_multiple_enrollments(self, enrollments, access_token, session):
        # 启动一个线程等待用户回车以停止所有线程
        stop_thread = Thread(target=self.wait_for_stop)
        stop_thread.start()

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(EnrollmentSubmitter(
                    eid, access_token, session, self.stop_event).run)
                for eid in enrollments
            ]
            try:
                for future in as_completed(futures):
                    future.result()
            except Exception as e:
                console.print(f"[red][!] 报名任务失败：{e}[/red]")

        # 等待停止线程结束
        stop_thread.join()

    def wait_for_stop(self):
        input("[!] 按回车键停止所有任务...\n")
        self.stop_event.set()  # 设置停止事件

    def run(self):
        clear_screen()
        access_token = self.login_with_phone()
        if not access_token:
            return

        user_history = []
        result = self.session.get(f'{self.user_history_url}{
                                  access_token}', headers=self.get_headers()).json()

        for entry in result['data']:
            if entry['status'] < 2:
                status = '进行中' if entry['status'] else '未开始'
                user_history.append(
                    {'name': entry['title'], 'status': status, 'eid': entry['eid']})

        if not user_history:
            console.print('[red][!] 请将需要提交的报名添加到个人记录中再运行程序[/red]')
            return

        console.print("[bold cyan]选择输入选项：[/bold cyan]")
        console.print("  - 输入 [yellow]all[/yellow] 并发报名所有任务")
        console.print("  - 输入 [yellow]ch[/yellow] 手动选择多个序号并发报名")
        console.print("  - 输入 [yellow]r[/yellow] 刷新记录")
        console.print("  - 按回车退出程序\n")

        while True:
            self.show_user_history(user_history)
            user_input = input(
                '[!] 请输入序号（输入"r"刷新记录，"all"并发报名所有任务，"ch"手动选择多个序号）：')
            if user_input.lower() == 'r':
                # 刷新记录
                user_history = []
                result = self.session.get(f'{self.user_history_url}{
                                          access_token}', headers=self.get_headers()).json()
                for entry in result['data']:
                    if entry['status'] < 2:
                        status = '进行中' if entry['status'] else '未开始'
                        user_history.append(
                            {'name': entry['title'], 'status': status, 'eid': entry['eid']})
                if not user_history:
                    console.print('[red][!] 请将需要提交的报名添加到个人记录中再运行程序[/red]')
            elif user_input.lower() == 'all':
                # 并发提交所有任务
                eid_list = [entry['eid'] for entry in user_history]
                self.run_multiple_enrollments(
                    eid_list, access_token, self.session)
                break
            elif user_input.lower() == 'ch':
                selected_indices = input('[!] 输入多个序号（用逗号分隔，如：1,3,5）：')
                try:
                    indices = [int(i.strip()) -
                               1 for i in selected_indices.split(',')]
                    eid_list = [user_history[i]['eid']
                                for i in indices if 0 <= i < len(user_history)]
                    if eid_list:
                        self.run_multiple_enrollments(
                            eid_list, access_token, self.session)
                    else:
                        console.print("[red][!] 未选择有效的序号，请重新输入。[/red]")
                except (ValueError, IndexError):
                    console.print("[red][!] 输入无效，请检查序号是否正确。[/red]")
                break
            elif user_input.isdigit() and 0 < int(user_input) <= len(user_history):
                selected_index = int(user_input) - 1
                EnrollmentSubmitter(
                    user_history[selected_index]['eid'], access_token, self.session, self.stop_event).run()
                break
            else:
                console.print('[red][!] 请输入正确的选项或序号[/red]')


if __name__ == '__main__':
    TokenRetriever().run()
    input('[!] 按回车退出...')
