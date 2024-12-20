import time
import json
import requests
import os
import base64
from rich.table import Table
from rich.console import Console
from threading import Event, Thread
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image
from io import BytesIO
#from fake_useragent import UserAgent

console = Console()

def clear_screen():

    os.system('cls' if os.name == 'nt' else 'clear')

    console.print("\n[bold cyan]----------------------------------------------------[/bold cyan]")
    console.print("           微信报名工具抢讲座小工具[bold cyan]v3.0.1[/bold cyan]")
    console.print("                     By C3ngH & void2eye")
    console.print("                      Updated: 2024-12-02")
    console.print("[bold cyan]----------------------------------------------------[/bold cyan]\n")

# def get_random_user_agent():

#     ua = UserAgent()
#     return ua.random


class EnrollmentSubmitter:


    def __init__(self, enrollment_id, access_token, session, stop_event):

        self.user_extra_info = {}
        self.enrollment_request_data = []
        self.access_token = access_token
        self.enrollment_id = enrollment_id
        self.base_url = 'https://api-xcx-qunsou.weiyoubot.cn/xcx/enroll'
        self.user_info_url = f'{self.base_url}/v1/userinfo?access_token={self.access_token}'
        self.request_details_url = f'{self.base_url}/v1/req_detail?access_token={self.access_token}&eid={self.enrollment_id}'
        self.submit_url = f'{self.base_url}/v5/enroll'
        self.failed_attempts = 0
        self.failed_attempts_limit = 20
        self.session = session
        self.stop_event = stop_event

    def get_headers(self):

        # return {'User-Agent': get_random_user_agent()}
        return {'User-Agent': 'Mozilla/5.0 (Windows NT 6.2; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/60.0.3112.90 Safari/537.36'}

    def fetch_user_info(self):

        response = self.session.get(self.user_info_url, headers=self.get_headers())
        user_info = response.json()

        for item in user_info['data']['extra_info']:
            names = item['name'] if isinstance(item['name'], list) else [item['name']]

            for name in names:
                self.user_extra_info[name] = item['value']

        console.print("\n[green]=== 用户信息已成功获取 ===[/green]")

        for name, value in self.user_extra_info.items():

            console.print(f"  - [yellow]{name}[/yellow]: {value}")

        console.print("\n[green]=== 开始抢讲座 ===[/green]")

    def fetch_enrollment_details(self):

        try:

            response = self.session.get(self.request_details_url, headers=self.get_headers())
            enrollment_data = response.json()

        except json.JSONDecodeError:

            console.print(f"{time.strftime('%H:%M:%S')} | [red][!] 获取报名详情失败[/red]")
            return False
        
        if not enrollment_data['data']['req_info']:

            console.print(f"{time.strftime('%H:%M:%S')} | [yellow][-] 报名尚未开始[/yellow]")
            return False
        
        for item in enrollment_data['data']['req_info']:

            field_value = self.user_extra_info.get(item['field_name'], '1' * item.get('min_length', 11))
            
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

        response = self.session.post(self.submit_url, json=body, headers=self.get_headers()).json()
        
        if response['sta'] == 0:
            console.print(f"{time.strftime('%H:%M:%S')} | [green][+] 报名已成功提交！[/green]")
            return True
        
        console.print(f"{time.strftime('%H:%M:%S')} | [red][-] 提交失败，返回信息: {response['msg']}[/red]")
        
        self.failed_attempts += 1
        return False

    def run(self):

        self.fetch_user_info()

        while self.failed_attempts < self.failed_attempts_limit and not self.stop_event.is_set():
            
            if self.fetch_enrollment_details():
                if self.submit_enrollment():
                    break

            time.sleep(0.2)

        if self.failed_attempts >= self.failed_attempts_limit:
            console.print("[red][!] 提交失败次数已达到%d次, 停止运行。[/red]" % self.failed_attempts_limit)


class TokenRetriever:


    def __init__(self):

        self.base_url = 'https://api-xcx-qunsou.weiyoubot.cn/xcx/enroll'
        self.qr_login_url = f'{self.base_url}_web/v1/pc_login?code='
        self.get_qr_url = f'{self.base_url}_web/v1/pc_code'
        self.user_history_url = f'{self.base_url}/v1/user/history?access_token='
        self.session = requests.Session()
        self.stop_event = Event()

    def get_headers(self):

        # return {'User-Agent': get_random_user_agent()}
        return {'User-Agent': 'Mozilla/5.0 (Windows NT 6.2; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/60.0.3112.90 Safari/537.36'}

    def login_with_qr_code(self):

        response = self.session.get(self.get_qr_url, headers=self.get_headers())
        qr_data = response.json()
        code = qr_data['data']['code']
        qr_code_base64 = qr_data['data']['qrcode'][22:]
        qr_code_data = base64.b64decode(qr_code_base64)

        image = Image.open(BytesIO(qr_code_data))

        console.print('[!] 请使用微信扫描二维码以登录')
        console.print('[!] 如不慎关闭窗口请按 [yellow]Ctrl+C[/yellow] 重新启动程序\n')

        image.show()
        
        while True:

            login_response = self.session.get(self.qr_login_url + code, headers=self.get_headers()).json()
            
            if login_response['sta'] == 0:

                console.print('[green][+] 登录成功！[/green]')
                return login_response['data']['access_token']
            
            time.sleep(1)

    def show_user_history(self, history_data):

        console.print('\n[!] 请选择要提交的表单序号')

        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("序号", style="dim")
        table.add_column("名称", style="bold")
        table.add_column("状态", style="green")

        for idx, entry in enumerate(history_data, 1):
            table.add_row(str(idx), entry['name'], entry['status'])

        console.print(table)

    def wait_for_stop(self):

        input("[!] 按回车键停止所有任务...\n")
        self.stop_event.set()

    def run_multiple_enrollments(self, enrollments, access_token):

        stop_thread = Thread(target=self.wait_for_stop)
        stop_thread.start()

        with ThreadPoolExecutor(max_workers=5) as executor:

            futures = [
                executor.submit(EnrollmentSubmitter(eid, access_token, self.session, self.stop_event).run)
                for eid in enrollments
            ]

            for future in as_completed(futures):
                future.result()

        stop_thread.join()

    def run(self):

        clear_screen()

        access_token = self.login_with_qr_code()

        if not access_token:
            return
        
        while True:

            user_history = []
            result = self.session.get(f'{self.user_history_url}{access_token}', headers=self.get_headers()).json()
            
            for entry in result['data']:

                if entry['status'] < 2:
                    status = '进行中' if entry['status'] else '未开始'
                    user_history.append({'name': entry['title'], 'status': status, 'eid': entry['eid']})
            
            self.show_user_history(user_history)
            
            console.print("[bold cyan]选择输入选项: [/bold cyan]")
            console.print("  - 输入 [yellow]all[/yellow] 并发报名所有任务")
            console.print("  - 输入 [yellow]ch[/yellow] 手动选择多个序号并发报名")
            console.print("  - 输入 [yellow]r[/yellow] 刷新记录")
            console.print("  - 按 [yellow]Ctrl+C[/yellow] 退出程序\n")
            
            user_input = input('[!] 请输入要报名的活动序号\n(输入"r"刷新记录，"all"并发报名所有任务，"ch"可手动选择多个序号，单个任务请直接输入序号): ')
            
            if user_input.lower() == 'r':
                continue

            elif user_input.lower() == 'all':

                eid_list = [entry['eid'] for entry in user_history]
                self.run_multiple_enrollments(eid_list, access_token)

                break

            elif user_input.lower() == 'ch':

                selected_indices = input('[!] 输入多个序号(用逗号分隔，如: 1,3,5): ')

                try:

                    indices = [int(i.strip()) - 1 for i in selected_indices.split(',')]
                    eid_list = [user_history[i]['eid'] for i in indices if 0 <= i < len(user_history)]
                    
                    if eid_list:
                        self.run_multiple_enrollments(eid_list, access_token)
                    
                    else:
                        console.print("[red][!] 未选择有效的序号，请重新输入。[/red]")
               
                except (ValueError, IndexError):
                    console.print("[red][!] 输入无效，请检查序号是否正确。[/red]")
                
                break
            
            elif user_input.isdigit() and 0 < int(user_input) <= len(user_history):
                
                selected_index = int(user_input) - 1
                EnrollmentSubmitter(user_history[selected_index]['eid'], access_token, self.session, self.stop_event).run()
                
                break

            else:
                console.print('[red][!] 输入无效，请重试。[/red]')

if __name__ == '__main__':

    TokenRetriever().run()
    
    input('[!] 按回车退出...')