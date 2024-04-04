#!/usr/bin/python3 -u
# -u is needed to unbuffer print making everything go to syslog instantly 
import os, io, sys 
import argparse
import time 
from datetime import (
    datetime, 
    timedelta 
)
import traceback
import subprocess
import threading
import functools
import sqlite3
import numpy as np 
from systemd import journal
import smtplib
from email.message import EmailMessage


# recommended approach dict as global
config = { 
    'motion_data_path' : None,
    'motion_pictures_path' : None,
    'motion_movies_path' : None,
    'data_size' : 90.,
    'gmail_user' : 'eusoubrasileiro@gmail.com',
    'gmail_to' : 'aflopes7@gmail.com',
    'gmail_app_password' : {{ gmail_app_password }} ,
}

def background_task(interval_secs=15*60):
    def background_task_decorator(function):
        """Decorator for tasks to be run on background (Thread)
        exceptions are handled, `interval_secs` is the amount of time to wait between looped execution
        doesn't return function return value since on onother thread
        """
        @functools.wraps(function)
        def wrapper(*args, **kwargs):       
            def loop_func():
                while True:
                    try:                
                        function(*args, **kwargs)
                        time.sleep(interval_secs)
                    except Exception as e:
                        log_print(f"motion nvr :: python exception at {function.__name__}")
                        log_print(traceback.format_exc())          
            threading.Thread(target=loop_func).start()  
        return wrapper
    return background_task_decorator

#### email support

def make_email(title, msg):
    email = EmailMessage()
    email['Subject'] = title
    email['From'] = config['gmail_user']
    email['To'] = config['gmail_to']
    email.set_content(msg, subtype='html')
    return email
   
def send_email(msg, title="Motion NVR Server ERROR"):
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.ehlo()
            server.login(config['gmail_user'], config['gmail_app_password'])
            server.send_message(make_email(title, msg))
    except Exception as exception:
        print("Error: %s!\n\n" % exception)

@background_task(interval_secs=60*60) #  run every 1 hour 3600 seconds
def send_email_im_alive():
    """send e-mail information every 1 hour with number of events frpm all cameras"""
    # to avoid sqlite3.OperationalError: # database is locked timeout from 5 seconds to 2 minutes
    # https://stackoverflow.com/a/3172950/1207193
    with sqlite3.connect("/home/andre/motion.db", timeout=2*60) as con: #'/mnt/motion/motion.db'
        now_utc = int(time.time())# it is UTC by default
        cameras = dict(zip(('front-up', 'front-left', 'left-aisle', 'right-aisle', 'broken-static'), [0]*5))
        for row in con.execute(f"SELECT * FROM events WHERE start > {now_utc-60*60}"): 
            cameras[row[4]] = cameras[row[4]] + 1 # last hour events per cam
    log_print(f"motion nvr :: Events last 1H {cameras}")
    send_email(f"<br><br>server-time: {str(datetime.now())} Events -1H {str(cameras)}", "Motion NVR Server ALIVE")

# @background_task(interval_secs=10*60) # run every 10 minues
# def send_email_if_errors(since=timedelta(minutes=10)):
#     # j = journal.Reader()
#     # j.log_level(journal.LOG_INFO)
#     # j.add_match(_SYSTEMD_UNIT="motion.service")
#     # j.seek_realtime(datetime.now() - since)
#     # count = 0
#     # msgs = ''
#     # for entry in j:        
#     #     if '[ERR]' not in entry['MESSAGE']:
#     #         open_, close_ = '', ''
#     #     else:  # or use jinja2. Too overkill?            
#     #         count=count+1  
#     #         open_, close_ = '<font color="red">', '</font>'
#     #     msgs += f"{open_} {entry['__REALTIME_TIMESTAMP']} {entry['MESSAGE']} {close_} <br>"
#     # log_print(f"motion nvr :: total number of [ERR] {count}")
#     # if count > 0:
#     #     send_email(msgs)
#     # return count 
#     pass 


#### main helper tools

lock = threading.Lock()
# only need to lock when printing on main or background threads

def log_print(*args, **kwargs):
    with lock:    
        # by default print on stderr - shows on status of service
        if 'file' not in kwargs:
            kwargs['file'] = sys.stderr 
        print(time.strftime("%Y-%m-%d %H:%M:%S")," ".join(map(str,args)), flush=True,  **kwargs)

@background_task(interval_secs=15*60) # run every 15 minutes
def recover_space():
    """Run cleanning motion folders files reclaiming space used (older files first)
    Takes almost forever to compute disk usage size better run on another thread.
    """ 
    split_char=';;'
    print_format = f'%T@{split_char}%p{split_char}%s\n'
    def array_files(storage_path):
        result = subprocess.run(r"find " + storage_path + f" -type f -printf '{print_format}'", 
            stdout=subprocess.PIPE, shell=True, universal_newlines=True)        
        data = np.loadtxt(io.StringIO(result.stdout.replace(split_char, ';')), dtype=[('age', '<f8'),('path', 'U200'), ('size', 'i8')], delimiter=';')
        data.sort(order='age') # big numbers last means younger files last
        data = data[::-1] #  (reverse it)
        return data 
    # look at movies and pictures folders, ignoring root due database file there
    data = np.concatenate([ array_files(config['motion_pictures_path']), 
            array_files(config['motion_movies_path']) ])
    space_max = config['data_size']*1024**3 # maximum size to bytes    
    sizes = np.cumsum(data['size']) # cumulative folder size starting with younger ones
    space_usage = sizes[-1]
    msg = 'motion nvr :: data folders are {:.2f} GiB'.format(space_usage/(1024**3))
    if space_usage >= space_max : # only if folder bigger than maxsize 
        del_start = np.argmax(sizes >= space_max) # index where deleting should start             
        msg += ' :: recovering space. Deleting: {:} files'.format(len(sizes)-del_start)        
        for path in data['path'][del_start:]:            
            os.remove(path)
    log_print(msg)
    subprocess.run("find " + config['motion_pictures_path'] + " -type d -empty -delete", shell=True) # delete empty folders
    subprocess.run("find " + config['motion_movies_path'] + " -type d -empty -delete", shell=True) # delete empty folders
    # python pathlib or os is 1000x slower than find 
    # find saving timestamp, paths of files and size (recursive)
    # find /mnt/motion_data/pictures -type f -printf '%T@;;%p;;%s\n' 

def set_motion_config(dir_motion_data, data_size):
    """Sets the motion configuration files, paths 
    * motion_data: str
        sets `config['storage_path']`  -> target_dir (motion.conf)
    * data_size: float 
         sets `config['data_size']` maximum size folder to reclaim space
    """
    config['motion_data_path'] = dir_motion_data
    config['motion_pictures_path'] = os.path.join(dir_motion_data, 'pictures')
    config['motion_movies_path'] = os.path.join(dir_motion_data, 'movies')     
    config['data_size'] = data_size

    log_print("motion nvr :: config options")
    for key, value in config.items():
        log_print(key, value)

# this is for logging very odd and uggly things that should never happen or almost never happen
# everything else goes to stderr/syslog 
oddlog = open("/home/andre/motion_runner.log", 'w')
# to switch thread control between motion_main_loop() and check_nfs_share_alive()
nfs_condition = threading.Condition() 

class MotionSubprocessThread(threading.Thread):
    """Executes `motiond -d 6 -n` on subprocess.popen at "/usr/local/etc/motion" folder.
        1. logs it's output to (stderr default)
        2. terminates it when stop_event is set
        3. restarts it on any error
    """
    def __init__(self, stop_event, restart_condition):        
        """
        stop_event: threading.Event - to stop the subprocess
        restart_condition: threading.Condition - after stop to restart
        """
        super().__init__()
        self.command = ["/usr/local/bin/motiond", "-d", "6", "-n"]
        self.stop_event = stop_event
        self.restart_condition = restart_condition
        self.stop = True
        self.process = None 

    def terminate(self):
        if self.process.poll() is None:
            log_print("MotionSubprocess terminating")
            while self.process.poll() is None: 
                self.process.terminate()                
                self.process.wait(timeout=10)  # Wait for termination
            log_print("MotionSubprocess terminated") 
             
    def run(self):
        while True:
            try:
                self.process = subprocess.Popen(self.command, stderr=subprocess.PIPE, bufsize=0, text=True, cwd="/usr/local/etc/motion")                        
                while not self.stop_event.is_set(): # Read and process stderr while the subprocess is running (all logs are in stderr)                
                    line = self.process.stderr.readline()
                    log_print(line.strip('\n'))            
                self.stop_event.clear()
                self.stop = True            
                self.terminate() # Terminate the subprocess 
            except subprocess.CalledProcessError as e:
                # Handle subprocess termination due to an error (SEGFULT or similar)
                log_print(f"MotionSubprocess terminated with error code: {e.returncode}", file=oddlog)
                if e.returncode < 0:
                    log_print(f"MotionSubprocess terminated by signal: {-e.returncode}", file=oddlog)
                    # Handle specific signals (e.g., SIGSEGV, SIGABRT, etc.) if needed
                else:
                    log_print("MotionSubprocess terminated due to an unknown error", file=oddlog)
            except Exception as e:
                log_print(f"MotionSubprocess running subprocess: {e}", file=oddlog)
            finally:
                # only arrives here if self.stop_event.is_set() or exception happens
                if self.stop: # wait to be restarted
                    with self.restart_condition:  # notify we are ready to restart
                        self.restart_condition.notify()
                    with self.restart_condition:
                        self.restart_condition.wait() # wait to be restarted
                self.terminate() # make sure that the subprocess is really dead
                self.stop = False            
            

def motion_main_loop():   
    """
    Blocks main thread
    Spawns MotionSubprocessThread
    Checks thread events and conditions to stop/restart MotionSubprocessThread
    Due nfs share not mounted
    """
    stop_motion = threading.Event()
    restart_motion = threading.Condition()    
    motion_thread = MotionSubprocessThread(stop_event, restart_motion)
    motion_thread.start()    
    while True:    # if motion dies without ever nfs share unmounting? it will restart again 
        # wait being notified - then control comes back to here        
        with nfs_condition:
            nfs_condition.wait()             
        stop_event.set() # stop motion process
        with restart_motion: # wait to be notified that it is dead
            restart_motion.wait()
        # motion was terminated now transfer control to check_nfs_share_alive()
        # so it can remount nfs share
        with nfs_condition:
            nfs_condition.notify()        
        with nfs_condition: # wait until it finishes mounting the nfs share
            nfs_condition.wait() 
        with restart_motion:
            restart_motion.notify() # nfs is mounted - notify so motion can restart



@background_task(interval_secs=15*60) # run every 15 minutes
def check_nfs_share_alive():    
    if not os.path.ismount(config['motion_data_path']):
        log_print("motion nvr :: nfs share is not mounted :: Stopping Motion", file=oddlog)        
        with nfs_condition:             
            nfs_condition.notify() # transfer control to motion_main_loop()
        with nfs_condition: # must come back when motion has terminated 
            nfs_condition.wait() # means motion is dead and we can remount nfs share
        # -S to read password from stdin - this bellow is the only way to work when on systemd .service
        process = subprocess.Popen("sudo -S bash /usr/bin/mnt-motion-mount.sh".split(" "), 
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        passwd='type your password here'
        stdout, stderr = process.communicate(input=f'{paswd}\n'.encode()) 
        log_print("motion nvr :: popen mnt-motion mount stdout:", stdout.decode(), file=oddlog)
        log_print("motion nvr :: popen mnt-motion mount stderr:", stderr.decode(), file=oddlog)
        send_email("motion nvr :: nfs share remounted :: restarting Motion")
        log_print("motion nvr :: nfs share remounted :: restarting Motion", file=oddlog)
        with nfs_condition:
            nfs_condition.notify() # notify motion_main_loop() that nfs share is mounted


def main():        
    try:        
        log_print('motion nvr :: starting', file=oddlog)                
        # all background threads/tasks
        check_nfs_share_alive()  # check if NFS share is alive kill motion/remount if not      
        recover_space()             
        send_email_im_alive()                
        # motion_loop in Python Main Thread
        motion_main_loop() 
    except Exception as e:
        log_print("motion nvr :: python exception on main", file=oddlog)
        log_print(traceback.format_exc(), file=oddlog)        

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Motion NVR')
    parser.add_argument('-d','--data-path', help='Path to store videos and pictures (all data) -> target_dir (motion.conf)', required=True)    
    parser.add_argument('-m','--data-size', help='Maximum folder data size in GB to reclaim space (delete old)', required=False, default="550")
    args = parser.parse_args()
    set_motion_config(args.data_path, float(args.data_size))    
    main()
    
