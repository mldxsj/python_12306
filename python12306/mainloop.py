import datetime
import time

from logic.login.checkuser import OnlineCheckerTool
from logic.login.login import NormalLogin
from logic.login.passager import QueryPassengerTool
from logic.query.dispatcher import DispatcherTool
from config import Config
from logic.submit.fastsubmit import FastSubmitDcOrder
from logic.submit.submit import NormalSubmitDcOrder
from utils.send_email import send_email
from utils.log import Log


class Schedule(object):
    retry_login_time = Config.basic_config.retry_login_time
    order_id = ''
    order_tickets = []

    def login(self):
        count = 0
        while self.retry_login_time >= count:
            login_instance = NormalLogin()
            Log.v("正在为您登录")
            status, msg = login_instance.login()
            if not status:
                count += 1
                Log.e(msg)
                Log.v("登录失败, 重试{0}次".format(count)) if self.retry_login_time >= count else ""
                continue
            else:
                Log.v("登录成功")
                break
        if self.retry_login_time <= count:
            Log.v("重试次数已经超过设置")
            return False
        return True

    def online_checker(self):
        # 两分钟检测一次
        flag = OnlineCheckerTool.should_check_online(datetime.datetime.now())
        if flag:
            status, msg = OnlineCheckerTool.checker()
            OnlineCheckerTool.update_check_time()
            if not status:
                Log.v("用户登录失效, 正在为您重试登录")
                login_status = self.login()
                if not login_status:
                    return False, "重试登录失败"
            else:
                return status, msg
        else:
            status, msg = True, "用户状态检测:未到检测时间"
        return status, msg

    def online_checker_now(self):
        status, msg = OnlineCheckerTool.checker()
        OnlineCheckerTool.update_check_time()
        if not status:
            Log.v("用户登录失效, 正在为您重试登录")
            login_status = self.login()
            if not login_status:
                return False, "重试登录失败"
        else:
            return status, msg

    @staticmethod
    def query_passengers():
        return QueryPassengerTool.filter_by_config()

    def query_dispatch(self):
        pass

    @staticmethod
    def check_maintain():
        # 12306 系统维护时间
        now = datetime.datetime.now()
        morning_time = datetime.datetime(year=now.year,
                                         month=now.month,
                                         day=now.day,
                                         hour=6,
                                         minute=0
                                         )
        evening_time = datetime.datetime(year=now.year,
                                         month=now.month,
                                         day=now.day,
                                         hour=23,
                                         minute=0
                                         )
        if now > evening_time or now < morning_time:
            return True
        else:
            return False

    @staticmethod
    def delta_maintain_time():
        # 12306 系统维护时间
        now = datetime.datetime.now()
        morning_time = datetime.datetime(year=now.year,
                                         month=now.month,
                                         day=now.day,
                                         hour=5,
                                         minute=59,
                                         second=56
                                         )
        next_morning_time = datetime.datetime(year=now.year,
                                              month=now.month,
                                              day=now.day,
                                              hour=5,
                                              minute=59,
                                              second=56
                                              ) + datetime.timedelta(days=1)
        evening_time = datetime.datetime(year=now.year,
                                         month=now.month,
                                         day=now.day,
                                         hour=23,
                                         minute=0
                                         )
        if now > evening_time:
            return next_morning_time - now
        if now < morning_time:
            return morning_time - now

    def submit_order(self, data):
        for v in data:
            if Config.basic_config.fast_submit:
                submit = FastSubmitDcOrder(v[1], v[0])
            else:
                submit = NormalSubmitDcOrder(v[1], v[0])
            f = submit.run()
            if not f:
                continue
            else:
                self.order_id = submit.order_id
                self.order_tickets = submit.query_no_complete_order()
                break

    def run(self):
        if not self.login():
            return
        p_status = self.query_passengers()
        if not p_status:
            return
        if not Config.auto_code_enable:
            Log.v("未开启自动打码功能, 不检测用户登录状态")
        Log.v("正在查询车次余票信息")

        count = 0

        while True:
            if self.check_maintain():
                Log.v("12306系统每天 23:00 - 6:00 之间 维护中, 程序暂时停止运行")
                maintain_time = self.delta_maintain_time()
                Log.v("{0}小时 {1}分钟 {2}秒之后重新启动".format(
                    maintain_time.seconds // 3600,
                    (maintain_time.seconds // 60) % 60,
                    maintain_time.seconds % 3600 % 60))
                time.sleep(self.delta_maintain_time().total_seconds())
            if Config.auto_code_enable:
                status, msg = self.online_checker()
                Log.v(msg)

            dates = DispatcherTool.query_travel_dates
            for query_date in dates:
                Log.v("查询第 {0} 次".format(count))
                n = datetime.datetime.now()
                data = DispatcherTool.run(query_date)
                count += 1
                self.submit_order(data)
                DispatcherTool.output_delta_time(n)
                if self.order_id:
                    break
            if self.order_id:
                break

        Log.v("抢票成功，{notice}".format(
            notice="你已开启邮箱配置，稍后会收到邮件通知" if Config.email_notice_enable else "如需邮件通知请先配置"))
        Log.v("车票信息：")
        for order_ticket in self.order_tickets:
            print(order_ticket)

        # 抢票成功发邮件信息
        send_email(2, **{"order_no": self.order_id,
                         "ticket_info": "</br>".join([v.to_html() for v in self.order_tickets])})


if __name__ == "__main__":
    instance = Schedule()
    instance.run()
