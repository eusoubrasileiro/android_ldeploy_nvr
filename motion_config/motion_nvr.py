import time, datetime, os, subprocess, re
import os
from pathlib import Path
import socket
import sys
import subprocess
from concurrent.futures import ThreadPoolExecutor

__sd_card_path__ = '/mnt/media_rw/2152-10F4'
__motion_pictures_path__ = os.path.join(__sd_card_path__,'media/motion_data/pictures')
__motion_movies_path__ = os.path.join(__sd_card_path__,'media/motion_data/movies')
__motion_log_file__ = os.path.join('/home/android','motiond_log.txt')


cams = {'ipcam_frontwall' : {'ip' : '192.168.0.146', 'mac' : 'A0:9F:10:00:93:C6'}, 
  'ipcam_garage' :  { 'ip' : '192.168.0.102', 'mac' : 'A0:9F:10:01:30:D2'},
  'ipcam_kitchen' : {'ip' : '192.168.0.100', 'mac' : 'A0:9F:10:01:30:D8'}}

def print_motion_logs(proc_motion):
    def print_output(file):
        for line in iter(file.readline, ''):
            print(line, end='') # printing to stdout
        file.close()
    with ThreadPoolExecutor(2) as pool:
        pool.submit(print_output, proc_motion.stdout)
        pool.submit(print_output, proc_motion.stderr)
          
def progressbar(it, prefix="", size=60, file=sys.stdout):
    count = len(it)
    def show(j):
        x = int(size*j/count)
        file.write("%s[%s%s] %i/%i\r" % (prefix, "#"*x, "."*(size-x), j, count))
        file.flush()        
    show(0)
    for i, item in enumerate(it):
        yield item
        show(i+1)
    file.write("\n")
    file.flush()
    
def current_hosts():
    "get current /etc/hosts"
    with open('/etc/hosts', 'r') as f:
        text = f.read()
    ipcams = re.findall('(.+)\s{4,}(ipcam_.+)', text)
    for ip, name in ipcams:
        cams[name]['ip'] = ip


# repeater is modifying the last values of the mac address
def update_hosts():
    """not having dns-server or willing to install dd-wrt (dnsmasq) for while"""
    # default /etc/hosts file
    # python string formated
    hostsfile_default= "127.0.0.1       localhost\\n::1             localhost ip6-localhost ip6-loopback\\nff02::1         ip6-allnodes\\nff02::2         ip6-allrouters\\n"
    hostsfile_write_cmd = "sudo -- sh -c -e \"echo 'python_string_formated_lines' > /etc/hosts\""
    # hostsfile_write_cmd.replace('python_string_formated_lines', hostsfile_default)
    #"""192.168.0.51    ipcam_frontwall
    #192.168.0.52    ipcam_garage
    #192.168.0.53    ipcam_kitchen
    #"""
    # command that workss
    #sudo -- sh -c -e "echo '127.0.0.1       localhost\n::1             localhost ip6-localhost ip6-loopback\nff02::1         ip6-allnodes\nff02::2         ip6-allrouters\n' > /etc/hosts"
    current_hosts()
    print('motion nvr :: current hostname ips')
    for cam, cam_ip_mac in cams.items():
        print("{0:<30} {1:<30} {2:30}".format(cam, cam_ip_mac['ip'], cam_ip_mac['mac'])) 
          
    print('motion nvr :: updating /etc/hosts with nmap')    
    output = subprocess.check_output(['sudo', 'nmap', '-p', '554,80,5000', '-T4', '--min-hostgroup', '50', 
    '--max-rtt-timeout', '1000ms', '--initial-rtt-timeout', '300ms', '--max-retries', '5', '--host-timeout', '20m', 
    '--max-scan-delay', '1000ms',
    '192.168.0.0/24']).decode()
    #sudo nmap -p 554,80,5000 -T4 --min-hostgroup 50 --max-rtt-timeout 1000ms --initial-rtt-timeout 300ms --max-retries 3 \
    # --host-timeout 20m --max-scan-delay 1000ms 192.168.0.0/24

    ips = re.findall('\d{3}\.\d{3}\.\d{1}\.\d{1,3}', output)
    macs = re.findall('(?:[0-9A-F]{2}[:-]){5}(?:[0-9A-F]{2})', output)    
    for cam, cam_ip_mac in cams.items():
        for ip, mac in zip(ips, macs):
            # compare only the last 3 groups of hex values
            # since the repeater may have changed the first 3 groups
            if mac[-8:] == cam_ip_mac['mac'][-8:]: 
                cams.update({cam :  {'ip' : ip, 'mac' : mac} })  
                                
    print("motion nvr :: mac's found")
    print(macs)
    print('motion nvr :: updated hostname ips')    
    for cam, cam_ip_mac in cams.items():
        print("{0:<30} {1:<30} {2:30}".format(cam, cam_ip_mac['ip'], cam_ip_mac['mac']))
        
    hosts_cams_lines = [cam_ip_mac['ip']+' '*4+cam+'\\n' for cam, cam_ip_mac in cams.items() if cam_ip_mac['ip'] != '' ] # ignore empty ip's
    os.system(hostsfile_write_cmd.replace('python_string_formated_lines', 
          hostsfile_default+''.join(hosts_cams_lines)))

def get_size_avgfile(path):
    file_sizes = [p.stat().st_size for p in Path(path).rglob('*')]  
    total = sum(file_sizes)  
    return total, total/len(file_sizes)
    
def clean_folder_old(path='.', percent=50):
    # younger first
    files  = subprocess.check_output(['ls', '-t', path]).decode().split('\n')
    # number of files to remove
    ndelete = int(len(files)*percent/100.)
    # get oldest first
    files = files[::-1][:ndelete]
    print('motion nvr :: cleaning ', percent, ' percent files. Deleting: ', ndelete, ' files')
    for cfile in progressbar(files, "deleting old files: ", 50):
        cfile_path = os.path.join(path, cfile)
        if os.path.exists(cfile_path) and os.path.isfile(cfile_path):          
          os.remove(cfile_path)

def check_clean_sdcard():
    """wether clean motion folders on sdcard due 90% space used"""  
    output = subprocess.check_output(['df', __sd_card_path__]).decode().replace('\n',' ').split(' ')
    sdcard_usage = int(output[-3][:-1]) # in percent
    print('motion nvr :: sdcard usage is: ', sdcard_usage, ' percent')
    if sdcard_usage > 90:
        # remove 90% of oldest pictures
        clean_folder_old(__motion_pictures_path__, 90) 
        # remove 50% of oldest movies
        clean_folder_old(__motion_movies_path__, 50) 

def is_running_byname(name_contains):
    """return list of pid's of running processes or [] empty if not running"""
    output = subprocess.check_output(['sudo', 'ps', '-A', 'all']).decode()
    pss = output.split('\n')[1:-3]
    pids = []
    for ps in pss:
        if ps.find(name_contains) != -1:
          pid = int(re.findall('\d{3,}', ps)[1]) #PID
          pids.append(pid)
    return pids              

def kill_byname(name_contains,current_pid=os.getpid()):
    for pid in is_running_byname(name_contains):
        if pid == current_pid: # prevent suicide 
            continue
        print("motion nvr :: killing by name contains: ", name_contains, " and pid: ", pid)
        os.system('sudo kill '+ str(pid))

def is_running_motion():
    if is_running_byname('motiond'):
      return True
    return False
            
def kill_motion():    
    kill_byname('motiond')

def kill_python_nvr():
    kill_byname('motion_nvr.py')

def start_motion(): 
    print('motion nvr :: starting motion')   
    # run inside the configuration folder to guarantee those configurations are used    
    # &> stdout and stderr to file
    return subprocess.Popen('cd ~/android_ldeploy_nvr/motion_config && motiond -d 6', stdout=subprocess.PIPE, 
          stderr=subprocess.PIPE, shell=True, universal_newlines=True)
    # the bellow doesnt work to merge all logs in only one file
    # os.system('cd ~/android_ldeploy_nvr/motion_config && motiond -l ~/motiond_log.txt  &> ~/motiond_log.txt &')

def main():
    print('motion nvr :: starting system :: pid :', os.getpid())
    kill_python_nvr()
    kill_motion()
    check_clean_sdcard()    # should also clean log-file once in a while to not make it huge
    update_hosts()
    proc_motion = start_motion()
    detection=True    
    print_motion_logs(proc_motion)     # 2 threads running on background printing motion log messages
    while True:    
        if not is_running_motion(): # check if motion is running 
                # time to re-start motion
                proc_motion = start_motion()
                detection=True
        else: # running
            if not detection:
                if datetime.datetime.now().time() > datetime.time(hour=20) or datetime.datetime.now().time() < datetime.time(hour=6):
                    try: # start motion detection
                        for i in range(1,4):
                            output = subprocess.check_output(['curl', '-s',
                                'http://localhost:8088/'+str(i)+'/detection/start']).decode()
                    except Exception as e:
                        print("motion nvr :: could not set detection parameter exception: ", e)
                        continue # try again later
                    detection=True
            else: # detection running
                if datetime.datetime.now().time() < datetime.time(hour=20) and datetime.datetime.now().time() > datetime.time(hour=6):
                    try: # pause motion detection
                        for i in range(1,4):
                            output = subprocess.check_output(['curl', '-s',
                                'http://localhost:8088/'+str(i)+'/detection/pause']).decode()
                    except Exception as e:
                        print("motion nvr :: could not set detection parameter exception: ", e)
                        continue # try again later
                    detection=False  
        time.sleep(15*60) # every 15 minutes only
        check_clean_sdcard()    # should also clean log-file once in a while to not make it huge
        update_hosts()      
            
if __name__ == "__main__":
    main()