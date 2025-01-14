# use "pbs" for packaging...
# pip-run -> pyqt5
# pip-dev -> pyqt5-stubs
import sys
import os
import os.path
import functools
import platform
# windows
import subprocess
# extras
import datetime 
import time
from pathlib import Path
from queue import Queue
from typing import List, Optional, Tuple, Type, TypeVar
import webbrowser
# pyqt5
from PyQt5 import QtWidgets, uic
from PyQt5.QtCore import Qt, QThread, pyqtSignal, pyqtSlot, QObject, QFile, QTextStream, QTimer, QSortFilterProxyModel, QSize, QRect
from PyQt5.Qt import QApplication, QClipboard, QLabel, QMovie, QIcon, QProgressBar,QProgressDialog, QMessageBox
# Nitrokey 2
from pynitrokey import libnk as nk_api
# Nitrokey 3
from pynitrokey.nk3 import list as list_nk3
# import wizards and stuff
from setup_wizard import SetupWizard
from qt_utils_mix_in import QtUtilsMixIn
from about_dialog import AboutDialog
from key_generation import KeyGeneration
from change_pin_dialog import ChangePinDialog
from storage_wizard import Storage
from loading_screen import LoadingScreen
from edit_button_widget import EditButtonsWidget
from pin_dialog import PINDialog
from insert_nitrokey import InsertNitrokey
from windows_notification import WindowsUSBNotification
from pynitrokey_for_gui import Nk3Context, list, version, wink, nk3_update, nk3_update_helper, change_pin
from tray_notification import TrayNotification
from nk3_button import Nk3Button
#import nitropyapp.libnk as nk_api
import nitropyapp.ui.breeze_resources 
#pyrcc5 -o gui_resources.py ui/resources.qrc
import nitropyapp.gui_resources

class BackendThread(QThread):
    hello = pyqtSignal()

    job_q = Queue()

    def __del__(self):
        self.wait()

    def add_job(self, signal, func, *f_va, **f_kw):
        self.job_q.put((signal, func, f_va, f_kw))

    def stop_loop(self):
        self.add_job(None, None)

    def run(self):
        self.hello.emit()
        while True:
            # blocking job-wait-loop
            job = self.job_q.get()
            if job is None:
                continue
            signal, func, vargs, kwargs = job

            # func == None means stop/end thread asap!
            if func is None:
                break

            # eval `func`, emit signal with results
            res = func(*vargs, **kwargs)
            signal.emit(res or {})

########################################################################################
########################################################################################
########################################################################################
########################################################################################
# Define function to import external files when using PyInstaller.
# def resource_path(relative_path):
#     """ Get absolute path to resource, works for dev and for PyInstaller """
#     try:
#         # PyInstaller creates a temp folder and stores path in _MEIPASS
#         base_path = sys._MEIPASS
#     except Exception:
#         base_path = os.path.abspath(".")
#
#     return os.path.join(base_path, relative_path)


# Import .ui forms for the GUI using function resource_path()
#securitySearchForm = resource_path("securitySearchForm.ui")
#popboxForm = resource_path("popbox.ui")

#Ui_MainWindow, QtBaseClass = uic.loadUiType(securitySearchForm)
#Ui_PopBox, QtSubClass = uic.loadUiType(popboxForm)

#pyrcc4 -py3 resources.qrc -o resources_rc.py
########################################################################################
########################################################################################
########################################################################################
########################################################################################
#### nk3
################c++ code from cli.nk3.init
#logger = logging.getLogger(__name__) 
#### PWS related callbacks

class GUI(QtUtilsMixIn, QtWidgets.QMainWindow):

    sig_connected = pyqtSignal(dict)
    sig_disconnected = pyqtSignal()
    sig_lock = pyqtSignal(dict)

    sig_ask_pin = pyqtSignal(dict)
    sig_auth = pyqtSignal(dict, str)
    sig_confirm_auth = pyqtSignal(str)

    sig_status_upd = pyqtSignal(dict)

    sig_unlock_pws = pyqtSignal(dict)
    sig_unlock_hv = pyqtSignal(dict)
    sig_unlock_ev = pyqtSignal(dict)

    change_value = pyqtSignal(int)

    
    def __init__(self, qt_app: QtWidgets.QApplication):
        QtWidgets.QMainWindow.__init__(self)
        QtUtilsMixIn.__init__(self)
        self.backend_thread.hello.connect(self.backend_cb_hello)
        self.backend_thread.start()
        # linux
        if  platform.system() == "Linux":
            # pyudev stuff 
            import pyudev
            from pyudev.pyqt5 import MonitorObserver
            # start monitoring usb
            self.context = pyudev.Context()
            self.monitor = pyudev.Monitor.from_netlink(self.context)
            self.monitor.filter_by(subsystem='usb')
            self.observer = MonitorObserver(self.monitor)
            self.observer.deviceEvent.connect(self.device_connect)
            self.monitor.start()
        # windows
        if platform.system() == "Windows":
            print("OS:Windows")
           
            w = WindowsUSBNotification(self.detect_nk3, self.remove_nk3)
            #win32gui.PumpMessages()
            print("not trapped")
        
        ################################################################################
        # load UI-files and prepare them accordingly
        ui_dir = Path(__file__).parent.resolve().absolute() / "ui"
        ui_files = {
            "main": (ui_dir / "mainwindow_alternative.ui").as_posix(),
            "pin": (ui_dir / "pindialog.ui").as_posix()
        }

        self.load_ui(ui_files["main"], self)
        self.pin_dialog = PINDialog(qt_app)
        self.pin_dialog.load_ui(ui_files["pin"], self.pin_dialog)
        self.pin_dialog.init_gui()
        _get = self.get_widget
        _qt = QtWidgets

        ################################################################################
        # playground

        self.key_generation = KeyGeneration(qt_app)
        self.key_generation.load_ui(ui_dir / "key_generation.ui", self.key_generation)
        self.key_generation.init_keygen()

        self.about_dialog = AboutDialog(qt_app)
        self.about_dialog.load_ui(ui_dir / "aboutdialog.ui", self.about_dialog)
        
        self.setup_wizard = SetupWizard(qt_app)
        self.setup_wizard.load_ui(ui_dir / "setup-wizard.ui", self.setup_wizard)
        self.setup_wizard.init_setup()

        self.storage = Storage(qt_app)
        self.storage.load_ui(ui_dir / "storage.ui", self.storage)
        self.storage.init_storage()
        
        self.insert_Nitrokey = InsertNitrokey(qt_app)
        self.insert_Nitrokey.load_ui(ui_dir / "insert_Nitrokey.ui", self.insert_Nitrokey)
        self.insert_Nitrokey.init_insertNitrokey()

        self.change_pin_dialog = ChangePinDialog(qt_app)
        self.change_pin_dialog.load_ui(ui_dir / "change_pin_dialog.ui", self.change_pin_dialog)
        self.change_pin_dialog.init_change_pin()
        ################################################################################
        #### get widget objects
        
        ## wizard
 
        
        ## app wide widgets
        self.status_bar = _get(_qt.QStatusBar, "statusBar")
        self.menu_bar = _get(_qt.QMenuBar, "menuBar")
        self.tabs = _get(_qt.QTabWidget, "tabWidget")
        self.tab_otp_conf = _get(_qt.QWidget, "tab")
        self.tab_otp_gen = _get(_qt.QWidget, "tab_2")
        self.tab_pws = _get(_qt.QWidget, "tab_3")
        self.tab_settings = _get(_qt.QWidget, "tab_4")
        self.tab_overview = _get(_qt.QWidget, "tab_5")
        self.tab_fido2 = _get(_qt.QWidget, "tab_6")
        self.tab_storage = _get(_qt.QWidget, "tab_7")
        self.about_button = _get(_qt.QPushButton, "btn_about")
        self.help_btn = _get(_qt.QPushButton, "btn_dial_help")
        self.quit_button = _get(_qt.QPushButton, "btn_dial_quit") 
        self.settings_btn = _get(_qt.QPushButton, "btn_settings")
        self.lock_btn = _get(_qt.QPushButton, "btn_dial_lock")
        self.pro_btn =  _get(_qt.QPushButton, "pushButton_pro")
        self.storage_btn =  _get(_qt.QPushButton, "pushButton_storage")
        self.fido2_btn =  _get(_qt.QPushButton, "pushButton_fido2")
        self.others_btn = _get(_qt.QPushButton, "pushButton_others")
        self.l_insert_Nitrokey = _get(_qt.QFrame, "label_insert_Nitrokey")
        ## overview 
        self.unlock_pws_btn = _get(_qt.QPushButton, "PWS_ButtonEnable")
        self.frame_p = _get(_qt.QFrame, "frame_pro")
        self.frame_s = _get(_qt.QFrame, "frame_storage")
        self.frame_f = _get(_qt.QFrame, "frame_fido2")
        self.navigation_frame = _get(_qt.QFrame, "vertical_navigation")
        self.nitrokeys_window = _get(_qt.QScrollArea, "Nitrokeys") 

        self.layout_nk_btns = QtWidgets.QVBoxLayout()
        self.layout_nk_btns.setContentsMargins(0,0,0,0)
        self.layout_nk_btns.setSpacing(0)
        self.layout_nk_btns.setAlignment(Qt.AlignTop)

        self.hidden_volume = _get(_qt.QPushButton, "btn_dial_HV")
        ### nk3
        self.nk3_lineedit_uuid = _get(_qt.QLineEdit, "nk3_lineedit_uuid")
        self.nk3_lineedit_path = _get(_qt.QLineEdit, "nk3_lineedit_path")
        self.nk3_lineedit_version = _get(_qt.QLineEdit, "nk3_lineedit_version")
        self.update_nk3_btn = _get(_qt.QPushButton, "update_nk3_btn")
        #self.update_nk3_btn.hide()

        self.nitrokey3_frame = _get(_qt.QFrame, "Nitrokey3")
        self.buttonLayout_nk3 = _get(_qt.QVBoxLayout, "buttonLayout_nk3")
        self.progressBarUpdate = _get(_qt.QProgressBar, "progressBar_Update")
        self.progressBarUpdate.hide()
        ## PWS
        self.information_label = _get(_qt.QLabel, "label_16")
        self.scrollArea = _get(_qt.QScrollArea, "scrollArea")
        self.groupbox_parameter = _get(_qt.QWidget, "widget_parameters")
        self.groupbox_notes = _get(_qt.QWidget, "widget_notes")
        self.groupbox_secretkey = _get(_qt.QWidget, "widget_secretkey")
        self.expand_button_secretkey = _get(_qt.QPushButton, "expand_button_secret")
        self.expand_button_notes = _get(_qt.QPushButton, "expand_button_notes")
        self.expand_button_parameter = _get(_qt.QPushButton, "expand_button_parameter")
        self.groupbox_pws = _get(_qt.QWidget, "widget_pws")
        self.table_pws = _get(_qt.QTableWidget, "Table_pws")
        self.pws_editslotname = _get(_qt.QLineEdit, "PWS_EditSlotName")
        self.pws_editloginname = _get(_qt.QLineEdit, "PWS_EditLoginName")
        self.pws_editpassword = _get(_qt.QLineEdit, "PWS_EditPassword")
        self.pws_editnotes = _get(_qt.QTextEdit, "textEdit_notes")
        self.pws_editOTP = _get(_qt.QLineEdit, "PWS_EditOTP")
        self.add_pws_btn = _get(_qt.QPushButton, "PWS_ButtonAdd")
        self.delete_pws_btn = _get(_qt.QPushButton, "PWS_ButtonDelete")
        self.cancel_pws_btn_2 = _get(_qt.QPushButton, "PWS_ButtonClose")
        self.add_table_pws_btn = _get(_qt.QPushButton, "PWS_ButtonSaveSlot")
        self.searchbox = _get(_qt.QLineEdit, "Searchbox")
        self.show_hide_btn = _get(_qt.QCheckBox, "show_hide")
        self.show_hide_btn_2 = _get(_qt.QCheckBox, "show_hide_2")
        self.pop_up_copy = _get(_qt.QLabel, "pop_up_copy")
        self.copy_name = _get(_qt.QPushButton, "copy_1")
        self.copy_username = _get(_qt.QPushButton, "copy_2")
        self.copy_pw = _get(_qt.QPushButton, "copy_3")
        self.copy_otp = _get(_qt.QPushButton, "copy_4")
        self.copy_current_otp = _get(_qt.QPushButton, "pushButton_otp_copy")
        self.qr_code = _get(_qt.QPushButton, "pushButton_4")
        self.random_otp = _get(_qt.QPushButton, "pushButton_7")
        
        ## smartcard
        self.pushButton_add_key = _get(_qt.QPushButton, "pushButton_add_keys")
        self.main_key = _get(_qt.QGroupBox, "groupBox_mainkey")
        self.sub_key_key = _get(_qt.QGroupBox, "groupBox_subkey")
        ## FIDO2
        self.add_btn = _get(_qt.QPushButton, "pushButton_add")
        self.table_fido2 = _get(_qt.QTableWidget, "Table_fido2")
        # OTP widgets
        self.radio_hotp_2 = _get(_qt.QRadioButton, "radioButton")
        self.radio_totp_2 = _get(_qt.QRadioButton, "radioButton_2")
        self.frame_hotp = _get(_qt.QFrame, "frame_hotp")
        self.frame_totp = _get(_qt.QFrame, "frame_totp")
        #self.radio_hotp = _get(_qt.QRadioButton, "radioButton")
        #self.radio_totp = _get(_qt.QRadioButton, "radioButton_2")
        #self.otp_combo_box = _get(_qt.QComboBox, "slotComboBox")
        #self.otp_name = _get(_qt.QLineEdit, "nameEdit")
        #self.otp_len_label = _get(_qt.QLabel, "label_5")
        #self.otp_erase_btn = _get(_qt.QPushButton, "eraseButton")
        #self.otp_save_btn = _get(_qt.QPushButton, "writeButton")
        #self.otp_cancel_btn = _get(_qt.QPushButton, "cancelButton")
        #self.otp_secret = _get(_qt.QLineEdit, "secretEdit")
        #self.otp_secret_type_b32 = _get(_qt.QRadioButton, "base32RadioButton")
        #self.otp_secret_type_hex = _get(_qt.QRadioButton, "hexRadioButton")
        #self.otp_gen_len = _get(_qt.QSpinBox, "secret_key_generated_len")
        #self.otp_gen_secret_btn = _get(_qt.QPushButton, "randomSecretButton")
        #self.otp_gen_secret_clipboard_btn = _get(_qt.QPushButton, "btn_copyToClipboard")
        #self.otp_gen_secret_hide = _get(_qt.QCheckBox, "checkBox")
        ################################################################################
        # set some props, initial enabled/visible, finally show()
        self.setAttribute(Qt.WA_DeleteOnClose)

        #self.tabs.setCurrentIndex(0)
        self.tabs.setCurrentWidget(self.tab_overview)
        self.tabs.currentChanged.connect(self.slot_tab_changed)

        self.init_gui()
        self.show()

        self.device = None

        ################################################################################
        ######nk3
        self.help_btn.clicked.connect(lambda:webbrowser.open('https://docs.nitrokey.com/nitrokey3'))    
        #self.change_value.connect(self.setprogressbar)
        #self.update_nk3_btn.clicked.connect(lambda: nk3_update(self.ctx,0))
        #self.connect_signal_slots(lambda:self.update_nk3_btn.clicked, self.change_value, [GUI.setProgressVal], lambda:nk3_update(self.ctx,0))
        # Nitrokey 3 update
        #self.firmware_started=lambda:self.user_info("Firmware Update started")
        #self.update_nk3_btn.clicked.connect(lambda:self.backend_thread.add_job(self.change_value,nk3_update(self.ctx, 0)))
        #self.update_nk3_btn.clicked.connect(lambda:nk3_update(self.ctx, self.progressBarUpdate, 0))
        
        self.lock_btn.clicked.connect(self.slot_lock_button_pressed)
        self.unlock_pws_btn.clicked.connect(self.unlock_pws_button_pressed)
        self.about_button.clicked.connect(self.about_button_pressed)
        self.pro_btn.clicked.connect(self.pro_btn_pressed)
        self.storage_btn.clicked.connect(self.storage_btn_pressed)
        self.fido2_btn.clicked.connect(self.fido2_btn_pressed)
        ################################################################################
        #### connections for functional signals
        ## generic / global
        self.connect_signal_slots(self.pro_btn.clicked, self.sig_connected,
            [self.job_nk_connected, 
            ### otp_combo_box is missing
            #self.toggle_otp
            self.load_active_slot
            ], self.job_connect_device)
        #self.sig_status_upd.connect(self.update_status_bar)
        self.sig_disconnected.connect(self.init_gui)
        ## overview

        ### storage
        self.hidden_volume.clicked.connect(self.create_hidden_volume)
        self.storage.show_hidden_pw.stateChanged.connect(self.slot_hidden_hide)

        self.setup_wizard.button(QtWidgets.QWizard.FinishButton).clicked.connect(self.init_pin_setup)
        ## setup
        self.storage.button(QtWidgets.QWizard.FinishButton).clicked.connect(self.init_storage_setup)
        ## smart card
        self.pushButton_add_key.clicked.connect(self.add_key)
        self.key_generation.button(QtWidgets.QWizard.FinishButton).clicked.connect(self.loading)

        ## pws stuff (now in passwordsafe.py) not in use yet
        # self.table_pws.cellClicked.connect(self.table_pws_function)
        # self.add_pws_btn.clicked.connect(self.add_pws)
        # self.add_table_pws_btn.clicked.connect(self.add_table_pws)
        # self.cancel_pws_btn_2.clicked.connect(self.cancel_pws_2)
        # self.delete_pws_btn.clicked.connect(self.delete_pws)
        # self.ButtonChangeSlot.clicked.connect(self.change_pws)
        # self.copy_name.clicked.connect(self.copyname)
        # self.copy_username.clicked.connect(self.copyusername)
        # self.copy_pw.clicked.connect(self.copypw)
        # self.copy_otp.clicked.connect(self.copyotp)
        ### groupboxes pws
        # self.expand_button_parameter.clicked.connect(self.groupbox_parameters_collapse)
        # self.expand_button_notes.clicked.connect(self.groupbox_manageslots_collapse)
        # self.expand_button_secretkey.clicked.connect(self.groupbox_secretkey_collapse)
        # ##self.groupbox_pws.clicked.connect(self.groupbox_pws_collapse)
        # self.searchbox.textChanged.connect(self.filter_the_table)
        # self.searchbox.setPlaceholderText("Search")
        # self.show_hide_btn.stateChanged.connect(self.slot_pws_hide)
        # self.show_hide_btn_2.stateChanged.connect(self.slot_otp_hide)

        ## otp stuff
        self.radio_totp_2.clicked.connect(self.slot_toggle_otp_2)
        self.radio_hotp_2.clicked.connect(self.slot_toggle_otp_2)

        #self.radio_totp.toggled.connect(self.slot_toggle_otp)
        #self.radio_hotp.toggled.connect(self.slot_toggle_otp)

        #self.otp_combo_box.currentIndexChanged.connect(self.slot_select_otp)
        # self.otp_erase_btn.clicked.connect(self.slot_erase_otp)
        # self.otp_cancel_btn.clicked.connect(self.slot_cancel_otp)
        # self.otp_save_btn.clicked.connect(self.slot_save_otp)

        # self.otp_secret.textChanged.connect(self.slot_otp_save_enable)
        # self.otp_name.textChanged.connect(self.slot_otp_save_enable)

        # self.otp_gen_secret_btn.clicked.connect(self.slot_random_secret)
        # self.otp_gen_secret_hide.stateChanged.connect(self.slot_secret_hide)
        
        ## auth related
        self.sig_ask_pin.connect(self.pin_dialog.invoke)
        self.sig_auth.connect(self.slot_auth)
        self.sig_confirm_auth.connect(self.slot_confirm_auth)
        self.sig_lock.connect(self.slot_lock)
        # nk3 change pin
        
    #nk3 stuff
        
    def info_success(self):
        self.user_info(self, "success")

    ### experimental idea to differ between removed and added
    def device_connect(self):
        for dvc in iter(functools.partial(self.monitor.poll, 3), None):
            if dvc.action == "remove":  
                print("removed")
                self.remove_nk3()            
            elif dvc.action == "bind":
                print("BIND")
                # bind for nk3
                self.detect_nk3()
                # # bind for old nks
                # func1 = lambda w: (w.setEnabled(False), w.setVisible(False))
                # self.apply_by_name(["pushButton_storage","pushButton_pro", "btn_dial_HV"], func1) # overview
                # ############## devs for the libraries
                # devs = nk_api.BaseLibNitrokey.list_devices()
            
                # print(devs)
                # dev = None
                # if len(devs) > 0:
                #     _dev = devs[tuple(devs.keys())[0]]
                #     # enable and show needed widgets
                #     func = lambda w: (w.setEnabled(True), w.setVisible(True))
                #     if _dev["model"] == 1:
                #         dev = nk_api.NitrokeyPro()
                #         self.apply_by_name(["pushButton_pro", "btn_dial_HV"], func) # overview
                #     elif _dev["model"] == 2:
                #         dev = nk_api.NitrokeyStorage()
                #         self.apply_by_name(["pushButton_storage", "btn_dial_HV"], func) # overview 
                                
                                    
                #     else:
                #         #func = lambda w: (w.setEnabled(False), w.setVisible(False))
                #         #self.apply_by_name(["pushButton_storage","pushButton_pro", "btn_dial_HV"], func) # overview
                #         print("removed button(s)")
                #         self.msg("Unknown device model detected")
                #         return {"connected": False}
                

    def detect_nk3(self):
        if len(list_nk3()):
            list_of_added = [y.uuid for y in Nk3Button.get()]
            print("list of added:", list_of_added)
            for x in list_nk3():
                if  x.uuid() not in list_of_added:
                    self.device = x
                    uuid = self.device.uuid()
                    if uuid:
                        print(f"{self.device.path}: {self.device.name} {self.device.uuid():X}")
                    else:
                        print(f"{self.device.path}: {self.device.name}")
                        print("no uuid")
                    Nk3Button(self.device, self.nitrokeys_window, self.layout_nk_btns, self.nitrokey3_frame, self.nk3_lineedit_uuid, self.nk3_lineedit_path, self.nk3_lineedit_version, self.tabs, self.update_nk3_btn, self.progressBarUpdate, self.change_pin_open_dialog, self.change_pin_dialog, self.buttonLayout_nk3)
                    tray_connect = TrayNotification("Nitrokey 3", "Nitrokey 3 connected.","Nitrokey 3 connected.")
                    self.device = None
                    print("nk3 connected")
                    self.l_insert_Nitrokey.hide() 
                else: 
                    nk3_btn_same_uuid = [y for y in Nk3Button.get() if (y.uuid == x.uuid())]
                    for i in nk3_btn_same_uuid:
                        if x.path != i.path:
                            i.update(x)
        else:
            print("no nk3 in list. no admin?")
            tray_not_connect = TrayNotification("Nitrokey 3", "Nitrokey 3 not connected.","Nitrokey 3 not connected.")
    def remove_nk3(self):
        list_of_removed = []
        if len(list_nk3()):
            print("list nk3:", list_nk3())
            list_of_nk3s = [x.uuid() for x in list_nk3()]
            list_of_removed_help = [y for y in Nk3Button.get() if (y.uuid not in list_of_nk3s)]
            list_of_removed = list_of_removed + list_of_removed_help
        else:
            list_of_removed = list_of_removed + Nk3Button.get()
        for k in list_of_removed:
            k.__del__()
            Nk3Button.list_nk3_keys.remove(k)

    ### helper (not in use for now)
    def get_active_otp(self):
        who = "totp" if self.radio_totp_2.isChecked() else "hotp"
        idx = self.otp_combo_box.currentIndex()
        return who, idx, self.device.TOTP if who == "totp" else self.device.HOTP,
        ############## get the current password slots from the key
    @pyqtSlot()
    def load_active_slot_name(self):
        if self.device is not None:
            return self.device.TOTP
        else:
            print("device is none")
    def load_active_slot(self):
        all_otp = self.load_active_slot_name()
        for index in range(10):
            name = all_otp.get_name(index)
            if name:
                self.add_table_pws_from_key(index)
                              
    def ask_pin(self, who):
        assert who in ["user", "admin"]
        who_cap = who.capitalize()
        dct = dict(
                title=f"{who_cap} PIN:",
                retries=self.device.user_pin_retries if who == "user" else
                        self.device.admin_pin_retries,
                sig=self.sig_auth,
                default=self.device.default_user_pin if who == "user" else
                        self.device.default_admin_pin,
                who=who
        )

        self.sig_ask_pin.emit(dct)
        self.msg(f"need {who_cap} auth")
        return

    def msg(self, what):
        what = what if isinstance(what, dict) else {"msg": what}
        self.sig_status_upd.emit(what)
    ### helper (in use)
    #### overview
    @pyqtSlot()
    def create_hidden_volume(self):
        self.storage.exec()
    @pyqtSlot()
    def loading(self):
        self.loading_screen = LoadingScreen()
        #self.main_key.show()
        #self.sub_key_key.show()
    #### PIN setup
    @pyqtSlot()
    def init_pin_setup(self):
        self.tabs.setEnabled(True)
        self.user_info("You have successfully configured the User and Admin PIN.\n These can be changed at any time in the device settings.",title ="PIN configuration was successful")
 
    #### storage setup
    @pyqtSlot()
    def init_storage_setup(self):
        print("it works")
        self.user_info("You now have successfully created your hidden volume.  ",title ="Hidden Volume generation was successful")   
    #### smartcard
    @pyqtSlot()
    def add_key(self):
        self.key_generation.exec()

    def cancel_pws_2(self):
        self.set_visible(QtWidgets.QFrame, ["groupbox_pw"], True) #changed to true
        #self.set_enabled(QtWidgets.QFrame, ["groupbox_pw"], False)
        #self.set_enabled(QtWidgets.QPushButton, ["PWS_ButtonSaveSlot", "PWS_ButtonClose"], False)
    #### collapsing groupboxes
    def groupbox_parameters_collapse(self):
        self.collapse(self.groupbox_parameter, self.expand_button_parameter)
    def groupbox_manageslots_collapse(self):
        self.collapse(self.groupbox_notes, self.expand_button_notes)
    def groupbox_secretkey_collapse(self):
        self.collapse(self.groupbox_secretkey, self.expand_button_secretkey)
    @pyqtSlot(int)
    def slot_otp_hide(self, state):
        if state == 2:
            self.pws_editOTP.setEchoMode(QtWidgets.QLineEdit.Password)
        elif state == 0:
            self.pws_editOTP.setEchoMode(QtWidgets.QLineEdit.Normal)
    @pyqtSlot(int)
    def slot_pws_hide(self, state):
        if state == 2:
            self.pws_editpassword.setEchoMode(QtWidgets.QLineEdit.Password)
        elif state == 0:
            self.pws_editpassword.setEchoMode(QtWidgets.QLineEdit.Normal)
    @pyqtSlot(int)
    def slot_hidden_hide(self, state):
        if state == 0:
            self.storage.hidden_pw_1.setEchoMode(QtWidgets.QLineEdit.Password)
            self.storage.hidden_pw_2.setEchoMode(QtWidgets.QLineEdit.Password)
        elif state == 2:
            self.storage.hidden_pw_1.setEchoMode(QtWidgets.QLineEdit.Normal)
            self.storage.hidden_pw_2.setEchoMode(QtWidgets.QLineEdit.Normal)
    @pyqtSlot()
    def copyname(self):
        QApplication.clipboard().setText(self.pws_editslotname.text())
        # qtimer popup
        self.time_to_wait = 5
        self.pop_up_copy.setText("Data added to clipboard.") #{0} for time display
        self.pop_up_copy.setStyleSheet("background-color: #2B5DD1; color: #FFFFFF ; border-style: outset;" 
        "padding: 2px ; font: bold 20px ; border-width: 6px ; border-radius: 10px ; border-color: #2752B8;")
        self.pop_up_copy.show()
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.changeContent)
        self.timer.start()  
    def changeContent(self):
        self.pop_up_copy.setText("Data added to clipboard.")
        self.time_to_wait -= 1
        if self.time_to_wait <= 0:
                self.pop_up_copy.hide()
                self.timer.stop()
    def closeEvent(self, event):
        lambda:self.timer.stop()
        event.accept()
    def copyusername(self):
        QApplication.clipboard().setText(self.pws_editloginname.text())
        # qtimer popup
        self.time_to_wait = 5
        self.pop_up_copy.setText("Data added to clipboard.") #{0} for time display
        self.pop_up_copy.setStyleSheet("background-color: #2B5DD1; color: #FFFFFF ; border-style: outset;" 
        "padding: 2px ; font: bold 20px ; border-width: 6px ; border-radius: 10px ; border-color: #2752B8;")
        self.pop_up_copy.show()
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.changeContent)
        self.timer.start()  
    def copypw(self):
        QApplication.clipboard().setText(self.pws_editpassword.text())
        # qtimer popup
        self.time_to_wait = 5
        self.pop_up_copy.setText("Data added to clipboard.") #{0} for time display
        self.pop_up_copy.setStyleSheet("background-color: #2B5DD1; color: #FFFFFF ; border-style: outset;" 
        "padding: 2px ; font: bold 20px ; border-width: 6px ; border-radius: 10px ; border-color: #2752B8;")
        self.pop_up_copy.show()
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.changeContent)
        self.timer.start()  
    def copyotp(self):
        QApplication.clipboard().setText(self.pws_editOTP.text())
        # qtimer popup
        self.time_to_wait = 5
        self.pop_up_copy.setText("Data added to clipboard.") #{0} for time display
        self.pop_up_copy.setStyleSheet("background-color: #2B5DD1; color: #FFFFFF ; border-style: outset;" 
        "padding: 2px ; font: bold 20px ; border-width: 6px ; border-radius: 10px ; border-color: #2752B8;")
        self.pop_up_copy.show()
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.changeContent)
        self.timer.start()  

    #### FIDO2 related callbacks
    @pyqtSlot()
    def slot_toggle_otp_2(self):
        if self.radio_hotp_2.isChecked():
            self.radio_totp_2.setChecked(False)
            self.frame_hotp.show()
            self.frame_totp.hide()
        else:
            self.radio_hotp_2.setChecked(False)
            self.frame_totp.show()
            self.frame_hotp.hide()
#########################################################################################
# not in use for now
    #### OTP related callbacks
    @pyqtSlot()
    def slot_random_secret(self):
        self.otp_secret_type_hex.setChecked(True)
        cnt = int(self.otp_gen_len.text())
        self.otp_secret.setText(self.device.gen_random(cnt, hex=True).decode("utf-8"))

    @pyqtSlot()
    def slot_cancel_otp(self):
        _, _, otp_obj = self.get_active_otp()

        self.otp_secret.clear()
        self.slot_select_otp()

    @pyqtSlot()
    def slot_erase_otp(self):
        who, idx, otp_obj = self.get_active_otp()

        if not self.device.is_auth_admin:
            self.ask_pin("admin")
            return

        ret = otp_obj.erase(idx)
        if not ret.ok:
            self.msg(f"failed erase {who.upper()} #{idx + 1} err: {ret.name}")
        else:
            self.msg(f"erased {who.upper()} #{idx + 1}")
            self.slot_select_otp(idx)

    @pyqtSlot()
    def slot_otp_save_enable(self):
        self.otp_save_btn.setEnabled(True)
        self.otp_cancel_btn.setEnabled(True)

    @pyqtSlot()
    def slot_save_otp(self):
        who, idx, otp_obj = self.get_active_otp()

        if not self.device.is_auth_admin:
            self.ask_pin("admin")
            return

        name = self.otp_name.text()
        if len(name) == 0:
            self.user_err("need non-empty name")
            return

        secret = self.otp_secret.text()
        # @fixme: what are the secret allowed lengths/chars
        #if len(secret)

        ret = otp_obj.write(idx, name, secret)
        if not ret.ok:
            self.msg(f"failed writing to {who.upper()} slot #{idx+1} err: {ret.name}")
        else:
            self.msg(f"wrote {who.upper()} slot #{idx+1}")
            self.otp_secret.clear()
            self.slot_select_otp(idx)
    @pyqtSlot()
    def slot_select_otp(self, force_idx=None):
        who, idx, otp_obj = self.get_active_otp()

        if force_idx is not None and idx != force_idx:
            idx = force_idx
            self.otp_combo_box.setCurrentIndex(idx)

        if idx < 0 or idx is None:
            return

        name = otp_obj.get_name(idx)
        self.otp_name.setText(name)
        self.otp_combo_box.setItemText(idx, f"{who.upper()} #{idx+1} ({name})")

        if name:
            self.sig_status_upd.emit({"msg": otp_obj.get_code(idx)})

        self.otp_cancel_btn.setEnabled(False)
        self.otp_save_btn.setEnabled(False)

    @pyqtSlot()
    def slot_toggle_otp(self):
        who, idx, otp_obj = self.get_active_otp()
        if who == "totp":
            # labels
            self.otp_len_label.setText("TOTP length:")
            #self.set_visible(QtWidgets.QLabel, ["label_6"], False)
            self.set_visible(QtWidgets.QLabel, ["intervalLabel"], True)

            # spacers + spin-box
            self.set_visible(QtWidgets.QSpinBox, ["intervalSpinBox"], True)

            # moving seed
            self.set_visible(QtWidgets.QPushButton,
                ["setToRandomButton", "setToZeroButton"], False)
            self.set_visible(QtWidgets.QLineEdit, ["counterEdit"], False)
        else:
            # labels
            self.otp_len_label.setText("HOTP length:")
            self.set_visible(QtWidgets.QLabel, ["intervalLabel"], False)
            #self.set_visible(QtWidgets.QLabel, ["label_6"], True)

            # spacers + spin-box
            self.set_visible(QtWidgets.QSpinBox, ["intervalSpinBox"], False)

            # moving seed
            self.set_visible(QtWidgets.QPushButton,
                             ["setToRandomButton", "setToZeroButton"], True)
            self.set_visible(QtWidgets.QLineEdit, ["counterEdit"], True)

        # drop down contents
        self.otp_combo_box.clear()
        for idx in range(otp_obj.count):
            name = otp_obj.get_name(idx) or ""
            self.otp_combo_box.addItem(f"{who.upper()} #{idx+1} ({name})")
            if idx == 0:
                self.otp_name.setText(name)

    @pyqtSlot(int)
    def slot_secret_hide(self, state):
        if state == 2:
            self.otp_secret.setEchoMode(QtWidgets.QLineEdit.Password)
        elif state == 0:
            self.otp_secret.setEchoMode(QtWidgets.QLineEdit.Normal)

    @pyqtSlot(str)
    def slot_confirm_auth(self, who):
        self.unlock_pws_btn.setEnabled(False)
        self.lock_btn.setEnabled(True)

        self.msg(f"{who.capitalize()} authenticated!")

    @pyqtSlot(dict)
    def slot_lock(self, status):
        self.unlock_pws_btn.setEnabled(True)
        self.lock_btn.setEnabled(False)
        self.sig_disconnected.emit()

    #### app-wide slots
    @pyqtSlot(dict, str)
    def slot_auth(self, opts, pin=None):
        who = opts.get("who")
        assert who in ["user", "admin"]
        who_cap = who.capitalize()

        auth_func = self.device.user_auth if who == "user" else self.device.admin_auth
        if pin is not None and auth_func(pin).ok:
            self.sig_confirm_auth.emit(who)
            self.pin_dialog.reset()
            self.user_info(f"{who_cap} auth successful", parent=self.pin_dialog)
        else:
            self.user_err(f"The provided {who}-PIN is not correct, please retry!",
                          f"{who_cap} not authenticated",
                          parent=self.pin_dialog)
            self.ask_pin(who)
###############################################################################################

    @pyqtSlot()
    def init_gui(self):
        self.init_otp_conf()
        """self.init_otp_general()"""
        self.init_pws()
        # detect already connected nk3s
        self.detect_nk3()

    @pyqtSlot()
    def job_connect_device(self):
        devs = nk_api.BaseLibNitrokey.list_devices()
        dev = None
        if self.device is not None:
            return {"device": self.device, "connected": self.device.connected,
                    "status": self.device.status, "serial": self.device.serial}
        ####### "serial" to get the serial number
        if len(devs) > 0:
            _dev = devs[tuple(devs.keys())[0]]

            if _dev["model"] == 1:
                dev = nk_api.NitrokeyPro()
            elif _dev["model"] == 2:
                dev = nk_api.NitrokeyStorage()
            
            else:
                self.msg("Unknown device model detected")
                return {"connected": False}

            try:
                dev.connect()
                self.device = dev
            except nk_api.DeviceNotFound as e:
                self.device = None
                self.msg("Connection failed, already in use?")
                return {"connected": False}

        if not self.device.connected:
            self.device = None
            return {"connected": False}

        status = dev.status
        self.msg({"status": status, "connected": status["connected"]})

        return {"connected": status["connected"], "status": status, "device": dev}
    # no status bar for now
    #@pyqtSlot(dict)
    # def update_status_bar(self, res_dct):
    #     cur_msg = self.status_bar.currentMessage
    #     append_msg = lambda s: self.status_bar.showMessage(
    #         s + ((" || " + cur_msg().strip()) if cur_msg().strip() else ""))

    #     # directly show passed 'msg'
    #     if "msg" in res_dct:
    #         append_msg(res_dct["msg"])
    #         return

    #     # not connected, show default message
    #     if not res_dct.get("connected"):
    #         self.status_bar.showMessage("Not connected")
    #         return

    #     # connected, show status information (if available)
    #     info = res_dct.get("status")
    #     if info:
    #         append_msg(f"Device: {info['model'].friendly_name}")
    #         append_msg(f"Serial: {info['card_serial_u32']}")
    #         append_msg(f"FW Version: {info['fw_version'][0]}.{info['fw_version'][1]}")
    #         append_msg(f"PIN Retries - (Admin/User): "
    #                    f"{info['admin_pin_retries']}/{info['user_pin_retries']}")

    @pyqtSlot(dict)
    def job_nk_connected(self, res_dct):
        if not res_dct["connected"]:
            self.msg("Not connected")
            return

        info = res_dct["status"]

        # enable and show needed widgets
        func = lambda w: (w.setEnabled(True), w.setVisible(True))
        self.apply_by_name([#"tab_pws", "btn_dial_lock",    # overview
                            #"frame", #"groupbox_manageslots", "groupbox_parameters",      # otp
                            #"frame_4",                         # otp config
                            #"groupbox_pw"                          # pws
                           ], func)

        if info["model"] == nk_api.DeviceModel.NK_STORAGE:
            self.apply_by_name(["pushButton_storage", "btn_dial_HV"], func) # overview
        elif info["model"] == nk_api.DeviceModel.NK_PRO:
            self.apply_by_name(["pushButton_pro", "btn_dial_HV"], func) # overview
    #### backend callbacks
    @pyqtSlot()
    def backend_cb_hello(self):
        print(f"hello signaled from worker, started successfully")

    @pyqtSlot(int)
    def slot_tab_changed(self, idx):
        pass

    #### main-window callbacks
    @pyqtSlot()
    def pro_btn_pressed(self):
        self.tabs.show()
        for i in range(1, 4):
            self.tabs.setTabEnabled(i, True)
        self.tabs.setTabEnabled(4, False)
        self.tabs.setTabEnabled(5, False)
        # set stylesheet of tabwidget to QTabBar::tab:disabled { width: 0; height: 0; margin: 0; padding: 0; border: none; } if you want to make the tabs invisible.
        self.storage_btn.setChecked(False)
        self.fido2_btn.setChecked(False)
        self.frame_s.setVisible(False)
        self.frame_f.setVisible(False)
        self.frame_p.setVisible(True)
    @pyqtSlot()
    def storage_btn_pressed(self):
        self.tabs.show()
        for i in range(1, 5):
            self.tabs.setTabEnabled(i, True)
        self.tabs.setTabEnabled(5, False)
        self.pro_btn.setChecked(False)
        self.fido2_btn.setChecked(False)
        self.frame_s.setVisible(True)
        self.frame_f.setVisible(False)
        self.setup_wizard.exec()

    @pyqtSlot()
    def fido2_btn_pressed(self):
        self.tabs.show()
        for i in range (1,5):
            self.tabs.setTabEnabled(i, False)
        self.tabs.setTabEnabled(5, True)
        self.pro_btn.setChecked(False)
        self.storage_btn.setChecked(False)
        self.frame_s.setVisible(False)
        self.frame_f.setVisible(True)
        self.frame_p.setVisible(False)

    @pyqtSlot()
    def about_button_pressed(self):
        self.about_dialog.show()

    def change_pin_open_dialog(self):
        self.change_pin_dialog.show()
        ##test
    @pyqtSlot()
    def slot_lock_button_pressed(self):
        # removes side buttos for nk3 (for now)  
        print("locked")        
        for x in Nk3Button.get():
            x.__del__()

        #if not self.device.connected:
        #    self.msg({"connected": False})
        #    self.sig_disconnected.emit()
        #    return
        #self.device.lock()
        #self.msg("Locked device!")
        #self.sig_lock.emit(self.device.status)

    @pyqtSlot()
    def unlock_pws_button_pressed(self):
        if not self.device.connected:
            self.msg({"connected": False})
            self.sig_disconnected.emit()
            return
        self.ask_pin("user")

    #### init main windows
    @pyqtSlot()
    def init_overview(self):
        names = ["btn_dial_EV", "btn_dial_HV", "btn_dial_PWS", "btn_dial_lock"]
        self.set_enabled(QtWidgets.QPushButton, names, False)

    @pyqtSlot()
    def init_otp_conf(self):
        #self.set_enabled(QtWidgets.QGroupBox, ["groupbox_pw", "groupbox_manageslots", "groupbox_parameters"], False)
        #self.set_enabled(QtWidgets.QPushButton, ["writeButton", "cancelButton"], False)
        #btns = ["setToRandomButton", "setToZeroButton"]
        #self.set_visible(QtWidgets.QPushButton, btns, False)
        #lbls = ["l_supportedLength", "labelNotify", "label_6"]
        #self.set_visible(QtWidgets.QLabel, lbls , False)
        self.set_visible(QtWidgets.QProgressBar, ["progressBar"], False)
        #self.set_visible(QtWidgets.QLineEdit, ["counterEdit"], False)
        self.radio_totp_2.setChecked(True)
        self.radio_hotp_2.setChecked(False)
        #self.set_visible(QtWidgets.QFrame, ["groupbox_manageslots", "groupbox_parameters"], False)
    """@pyqtSlot()
    def init_otp_general(self):
        self.set_enabled(QtWidgets.QFrame, ["frame_4"], False)
        names = ["generalCancelButton", "writeGeneralConfigButton"]
        self.set_enabled(QtWidgets.QPushButton, names, False)"""

    @pyqtSlot()
    def init_pws(self):
        btn_cls = QtWidgets.QPushButton
        #self.set_visible(QtWidgets.QFrame, ["groupbox_pw"], False)
        #self.set_enabled(QtWidgets.QFrame, ["groupbox_pw"], False)
        self.set_visible(btn_cls, ["PWS_Lock"], False)
        self.set_visible(QtWidgets.QProgressBar, ["PWS_progressBar"], False)
        names = ["PWS_ButtonEnable", "PWS_ButtonSaveSlot", "PWS_ButtonClose"]
        #self.set_enabled(btn_cls, names, False)
        #self.set_enabled(QtWidgets.QLabel, ["l_utf8_info"], False)
        self.collapse(self.groupbox_parameter,  self.expand_button_parameter)
        self.collapse(self.groupbox_notes,  self.expand_button_notes)
        self.collapse(self.groupbox_secretkey, self.expand_button_secretkey)
        #self.groupbox_secretkey.hide()
        self.ButtonChangeSlot.setVisible(False)
        self.PWS_ButtonDelete.setVisible(False)
        hide_list = [self.frame_pro, self.frame_fido2, self.frame_storage, self.frame_hotp, self.expand_button_secret, self.scrollArea, self.information_label, self.copy_current_otp, self.main_key, self.sub_key_key, self.tabs, self.pro_btn, self.storage_btn, self.fido2_btn]
        for x in hide_list:
            x.hide()
        self.show()

def main():
    # backend thread init
    QtUtilsMixIn.backend_thread = BackendThread()

    app = QtWidgets.QApplication(sys.argv)
  
    # set stylesheet
    file = QFile(":/light.qss")
    file.open(QFile.ReadOnly | QFile.Text)
    stream = QTextStream(file)
    #app.setStyleSheet(stream.readAll())
    window = GUI(app)
    app.exec()

if __name__ == "__main__":
    main()
    