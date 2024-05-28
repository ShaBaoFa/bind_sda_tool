# -*- coding: utf-8 -*-
import logging
import time
# Form implementation generated from reading ui file 'gui.ui'
#
# Created by: PyQt5 UI code generator 5.15.9
#
# WARNING: Any manual changes made to this file will be lost when pyuic5 is
# run again.  Do not edit this file unless you know what you are doing.
from queue import Queue
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtWidgets import QFileDialog, QApplication, QMainWindow, QTableWidget, QTableWidgetItem, QVBoxLayout, \
    QWidget, QMenu, QMessageBox
from PyQt5.QtCore import QThread, QObject, pyqtSignal, Qt
from openpyxl import Workbook

from mail import SteamMail
from steam import SteamAuth
from win_gui import Ui_task_MainWindow


class Worker(QThread, QObject):
    finished = pyqtSignal()
    update_table_item_request = pyqtSignal(int, int, str)
    get_table_item = pyqtSignal(int, int)

    def __init__(self, account, password, email, email_pwd, row_index, parent=None):
        QThread.__init__(self, parent)
        QObject.__init__(self, parent)
        self.account = account
        self.password = password
        self.email = email
        self.email_pwd = email_pwd
        self.row_index = row_index
        self.acc = None

    def run(self):
        try:
            login_state = self.login_task(self.account, self.password, self.email, self.email_pwd, self.row_index)
            if login_state:
                self.bind_task()
        except Exception as e:
            print(f'Exception in run: {e}')
        finally:
            self.finished.emit()

    def bind_task(self):
        self.update_table_item_request.emit(self.row_index, 5, '开始绑定')
        # 先获取邮箱当前邮件数,方便获取差值
        self.acc.mail = SteamMail('outlook.office365.com', self.acc.username,self.acc.email,self.acc.email_pwd)
        try:
            self.acc.mail.set_last_email_count()
        except Exception as e:
            self.update_table_item_request.emit(self.row_index, 5, '连接邮箱失败')
            return
        self.acc.add_authenticator()
        self.update_table_item_request.emit(self.row_index, 5, '获取邮箱验证码')
        success, verification_code = self.acc.get_mail_code()
        if not success:
            self.update_table_item_request.emit(self.row_index, 5, '获取邮箱验证码失败')
            return
        self.update_table_item_request.emit(self.row_index, 5, '绑定中.....')
        success = self.acc.finalize_add_authenticator(verification_code)
        if success:
            self.update_table_item_request.emit(self.row_index, 5, '绑定成功')
            self.update_table_item_request.emit(self.row_index, 6, f"{self.acc.ma_file.revocation_code}")
        else:
            self.update_table_item_request.emit(self.row_index, 5, '绑定失败')


    def login_task(self, account, password, email, email_pwd, row_index):
        self.acc = SteamAuth(account, password, email, email_pwd)
        # 先获取邮箱当前邮件数,方便获取差值
        rsa_state, rsa_re = self.acc.get_rsa_public_key()
        if rsa_state:
            encode_password = self.acc.rsa_encrypt(rsa_re.publickey_mod, rsa_re.publickey_exp)
            send_state, send_re = self.acc.send_encode_request(encode_password, rsa_re.timestamp)
            print(f'{send_re}')
            if send_state:
                if len(send_re.allowed_confirmations) > 0:
                    if send_re.allowed_confirmations[0].confirmation_type == 1:
                        res = self.acc.get_token()
                        if res:
                            self.update_table_item_request.emit(row_index, 5, '登陆成功')
                            return True
                        else:
                            self.update_table_item_request.emit(row_index, 5, '登陆失败')
                            return False
                    if send_re.allowed_confirmations[0].confirmation_type == 2:
                        self.update_table_item_request.emit(self.row_index, 5, '获取邮箱验证码...')
                        success, verification_code = self.acc.get_mail_code()
                        if not success:
                            self.update_table_item_request.emit(self.row_index, 5, '获取邮箱验证码失败')
                            return False
                        print(f'获取到的邮箱验证码: {verification_code}')
                        self.update_table_item_request.emit(self.row_index, 5, '登陆中.....')
                        success = self.acc.auth_code(code=verification_code,code_type=2)
                        if success:
                            token_state = self.acc.get_token()
                            if token_state:
                                self.update_table_item_request.emit(row_index, 1, '登录成功')
                                return True
                            else:
                                self.update_table_item_request.emit(row_index, 1, '登陆失败')
                                return False
                        return False
            else:
                self.update_table_item_request.emit(row_index, 5, '登陆失败')
                return False
        else:
            self.update_table_item_request.emit(row_index, 5, '获取密钥失败')
            return False


class Ui_MainWindow(QMainWindow, Ui_task_MainWindow):
    def __init__(self):
        # 初始化代码...
        self.taskQueue = Queue()  # 创建一个任务队列
        self.activeThreads = 0  # 当前活跃的线程数
        self.maxThreads = 1  # 最大并发线程数
        self.threadList = []  # 用于存储所有线程的列表
        self.workerList = []
        self.isRunning = False  # 追踪任务是否正在运行
        super(Ui_MainWindow, self).__init__()
        self.setupUi(self)  # 使用 Ui_MainWindow 来设置界面

    def update_table_item(self, row_index, col_index, text):
        item = self.accTable.item(row_index, col_index)
        if item:
            item.setText(text)
        else:
            self.accTable.setItem(row_index, col_index, QtWidgets.QTableWidgetItem(text))

    def get_table_item(self, row_index, col_index):
        item = self.accTable.item(row_index, col_index)
        if item:
            return item.text()
        else:
            return None

    def load_accounts_from_file(self):
        filePath, _ = QFileDialog.getOpenFileName(None, "选择账号文件", "", "Text Files (*.txt)")
        if filePath:
            with open(filePath, 'r', encoding='utf-8') as file:
                lines = file.readlines()
                self.accTable.setRowCount(len(lines))
                for rowIndex, line in enumerate(lines):
                    checkBoxItem = QtWidgets.QTableWidgetItem()
                    checkBoxItem.setCheckState(QtCore.Qt.Unchecked)
                    self.accTable.setItem(rowIndex, 0, checkBoxItem)
                    items = line.strip().split('----')
                    for columnIndex, item in enumerate(items):
                        if columnIndex < self.accTable.columnCount() and columnIndex < 4:
                            self.accTable.setItem(rowIndex, columnIndex + 1, QtWidgets.QTableWidgetItem(item))

    def toggle_task(self):
        if not self.isRunning:
            self.start_task()
        else:
            self.stop_task()

    def start_task(self):
        thread_num = int(self.threadNumEdit.text())  # 获取文本内容
        if thread_num:
            self.maxThreads = thread_num
        else:
            self.maxThreads = 1
        if self.accTable.rowCount() > 0:
            # 更新运行状态
            self.isRunning = 1
            self.startTaskBut.setText("停止")
            self.startTaskBut.setEnabled(True)
            self.threadList.clear()
            rowCount = self.accTable.rowCount()
            for rowIndex in range(rowCount):
                print(f'rowIndex: {rowIndex}')
                account = self.accTable.item(rowIndex, 1).text()
                password = self.accTable.item(rowIndex, 2).text()
                email = self.accTable.item(rowIndex, 3).text()
                email_pwd = self.accTable.item(rowIndex, 4).text()
                # 将任务参数作为元组加入队列
                self.taskQueue.put((account, password, email, email_pwd, rowIndex))

            # 尝试启动初始的一组线程
            for _ in range(min(self.maxThreads, self.taskQueue.qsize())):
                self.start_next_task()

    def stop_task(self):
        if len(self.workerList) == 0 and len(self.threadList) == 0:
            self.isRunning = 0
            self.startTaskBut.setText("开始")
            self.startTaskBut.setEnabled(False)  # 设置按钮为不可点击
        else:
            self.isRunning = 2
            self.startTaskBut.setText("停止中")
            self.startTaskBut.setEnabled(False)  # 设置按钮为不可点击

    def start_next_task(self):
        if not self.taskQueue.empty() and self.activeThreads < self.maxThreads and self.isRunning == 1:
            account, password, email, email_pwd, rowIndex = self.taskQueue.get()
            thread = QThread()
            worker = Worker(account, password, email, email_pwd, rowIndex)
            worker.moveToThread(thread)
            worker.update_table_item_request.connect(self.update_table_item)
            worker.get_table_item.connect(self.get_table_item)
            worker.finished.connect(lambda: self.on_task_finished(thread, worker))
            thread.started.connect(worker.run)

            thread.start()
            self.activeThreads += 1
            self.workerList.append(worker)
            self.threadList.append(thread)  # 将线程添加到列表中
        elif self.isRunning == 2 and len(self.workerList) == 0 and len(self.threadList) == 0:
            self.isRunning = 0
            self.startTaskBut.setText("开始")
            self.startTaskBut.setEnabled(True)

    def on_task_finished(self, thread, worker):
        # 线程完成时的清理工作
        thread.quit()
        thread.wait()
        thread.deleteLater()
        self.activeThreads -= 1
        try:
            self.workerList.remove(worker)
        except ValueError:
            pass  # 这里忽略错误，因为worker可能已经被移除
        self.threadList.remove(thread)  # 从列表中移除已完成的线程

        # 检查是否所有任务都已完成
        if self.taskQueue.empty() and self.activeThreads == 0:
            # 所有任务完成后的操作
            QMessageBox.information(None, "任务完成", "所有任务已经完成！")
            self.startTaskBut.setText("开始")
            self.startTaskBut.setEnabled(True)  # 重新启用开始按钮
            self.isRunning = 0  # 更新运行状态标记为不运行

        # 尝试启动下一个等待中的任务
        self.start_next_task()

    def openMenu(self, position):
        menu = QMenu()

        # 添加全选动作
        selectAllAction = menu.addAction("全选")
        selectAllAction.triggered.connect(self.selectAll)

        # 添加反选动作
        invertSelectionAction = menu.addAction("反选")
        invertSelectionAction.triggered.connect(self.invertSelection)

        # 添加删除选中行动作
        deleteSelectedAction = menu.addAction("删除选中行")
        deleteSelectedAction.triggered.connect(self.deleteSelectedRows)

        # 导出选中账号
        deleteSelectedAction = menu.addAction("导出选中账号")
        deleteSelectedAction.triggered.connect(self.exportSelectedRows)

        # 显示菜单
        menu.exec_(self.accTable.viewport().mapToGlobal(position))

    def selectAll(self):
        for i in range(self.accTable.rowCount()):
            self.accTable.item(i, 0).setCheckState(Qt.Checked)

    def invertSelection(self):
        for i in range(self.accTable.rowCount()):
            if self.accTable.item(i, 0).checkState() == Qt.Checked:
                self.accTable.item(i, 0).setCheckState(Qt.Unchecked)
            else:
                self.accTable.item(i, 0).setCheckState(Qt.Checked)

    def deleteSelectedRows(self):
        # 从后往前遍历，避免索引问题
        for i in range(self.accTable.rowCount() - 1, -1, -1):
            if self.accTable.item(i, 0).checkState() == Qt.Checked:
                self.accTable.removeRow(i)

    def exportSelectedRows(self):
        # 创建一个工作簿
        workbook = Workbook()
        sheet = workbook.active
        column_titles = ['账户', '密码', '邮箱', '邮箱密码', '救援码']
        sheet.append(column_titles)  # 将列标题添加到第一行
        # 遍历表格的每一行
        for i in range(self.accTable.rowCount()):
            if self.accTable.item(i, 0).checkState() == Qt.Checked:
                # 如果该行被选中，则将该行的所有列数据添加到工作表中
                rowData = []
                for j in range(self.accTable.columnCount()):
                    item = self.accTable.item(i, j)
                    if j == 0 or j == 5: continue
                    rowData.append(item.text() if item else "")
                sheet.append(rowData)
        # 弹出文件保存对话框，让用户选择保存位置和文件名
        fileName, _ = QFileDialog.getSaveFileName(None, "保存文件", "", "Excel文件 (*.xlsx)")

        if fileName:
            # 保存工作簿到指定的文件
            workbook.save(fileName)
            # 提示保存成功
            QMessageBox.information(None, "导出成功", f"账号信息已成功导出到 {fileName}")


import sys

if __name__ == "__main__":
    app = QApplication(sys.argv)
    MainWindow = QMainWindow()
    ui = Ui_MainWindow()
    ui.setupUi(MainWindow)
    MainWindow.show()
    sys.exit(app.exec_())
