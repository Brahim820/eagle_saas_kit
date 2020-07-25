import os,time,sys,shutil
import random, string
import json
import subprocess
import imp,re,shutil
import argparse
import logging
import functools
from collections import defaultdict
import socket
from contextlib import closing
from configparser import SafeConfigParser
import logging
from . import saas_client_db
_logger = logging.getLogger(__name__)
from .  pg_query import PgQuery 
import xmlrpc.client
try:
    import docker
except ImportError as e:
    _logger.info("Docker Library not installed!!")
     
try:
    import erppeek
except ImportError as e:
    _logger.info("erppeek library not installed!!")
        
 
  
class eagle_container:
     
    def  __init__(self,db="dummy",eagle_image="eagle:12.5",eagle_config = None,host_server = None, db_server = None):
        self.eagle_image = eagle_image
        self.location = eagle_config
        self.remote_host = host_server['host']
        self.remote_port = host_server['port']
        self.remote_user = host_server['user']
        self.remote_password = host_server['password']
        self.db_host = db_server['host']
        self.db_port = db_server['port']
        self.db_user = db_server['user']
        self.db_password = db_server['password']
        self.response = {}
        self.read_variables(self.location+"/models/lib/saas.conf")

    def read_variables(self,path):
        _logger.info("Reading Conf from %r"%path)
        parser = SafeConfigParser()
        parser.read(path)
        self.template_master = parser.get("options","template_master")
        self.container_master = parser.get("options","container_master")
        self.container_user = parser.get("options","container_user")
        self.eagle_config = parser.get("options","eagle_saas_data")
        self.container_passwd = parser.get("options","container_passwd")
        self.template_eagle_port = parser.get("options","template_eagle_port")
        self.common_addons = parser.get("options","common_addons")
        self.eagle_template = parser.get("options","eagle_template")
        self.data_dir = parser.get("options","data_dir_path")
        self.eagle_image = parser.get("options","eagle_image")
        self.response['eagle_image'] = self.eagle_image

    def get_client(self):
        try:
            self.dclient = docker.from_env()
        except Exception as e:
            _logger.info("Docker Library not installed!!")
            return False
        return True
    
    def check_error(self,func):
        functools.wraps(func)
        def wrapper(*args,**argc):
            try:
                return func(*args,**argc)
            except Exception as e:
                _logger.info("Error %s occurred at %s"%(str(e),func.__name__))
                exit(1)
        return wrapper

    def list_all_used_ports(self):
        containers = self.dclient.containers.list(all)
        used_ports = [8888] #8888 to be used for DB templates 
        for each in containers:
            port_info =  each.attrs['HostConfig']['PortBindings']
            if port_info and port_info.get('8069/tcp',None):
                used_ports.append(port_info['8069/tcp'][0]['HostPort'])
        return used_ports
    
    def find_me_an_available_port_within(self,a,b):
        ports_in_use = self.list_all_used_ports()
        _logger.info("++Ports already In use+%r",str(ports_in_use))
        for port in range(a, b):
             if str(port) in ports_in_use:
                 _logger.info("Port %r  already in use",port)
                 continue
             with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
                 res = sock.connect_ex(('localhost', port))
                 if res != 0:
                     self.response['port'] =  port
                     return port
        _logger.info("All the ports are being used. Try removing unused or obselete containers")
        return False
    
    def random_str(self,length):
        letters = string.ascii_uppercase
        return ''.join(random.choice(letters) for i in range(length))   
    
    def create_db(self,url,db,admin_passwd):
        _logger.info(type(url))
        _logger.info("Connection initiated %s"%url)
        count = 0
        client = ""
        while count < 10:
            try:
                _logger.info("Attempting %d. Eagle should be ready by now"%count)
                client = erppeek.Client(server=str(url))
                break
            except Exception as e:
                count += 1
                _logger.info("Error %r"%str(e))
                time.sleep(4)
        if count == 10:
           _logger.info("Connectio Could not be built")
           return False                

        _logger.info("Connection built %s"%url)
        try:
            client.create_database(admin_passwd,db) #using default admin password
            return True
        except Exception as e:
            _logger.info("Error",e)
            _logger.info("DB Create: %r"%(str(e)))
            return False
    
    def check_if_installed(self,program):
        return shutil.which(program)
    
    def remove_container(self,name): 
        try:
            cont = self.dclient.containers.get(name) #can fetch the data regarding all running or stopped containers.
            cont.remove(force=True)
            _logger.info("Container -->%s deleted"%name)
        except docker.errors.NotFound as e:
            _logger.info("%s is not available. Must have already been deleted"%name)

    def mkdir_OdooConfig(self,folder,conf_file):
        try:
            path = self.eagle_config+"/"+folder
            os.mkdir(path)
            shutil.copy(self.eagle_config+"/"+conf_file,path+"/eagle-server.conf") #TODO -manage file permissions
            _logger.info("Folder %s created"%path)
            self.response['path'] = path
            return path
        except OSError as e:
            _logger.info("Errro",e)
            raise e
    def mkdir_mnt_extra_addons(self, folder):
        try:
            path = self.eagle_config+"/"+folder+"/data-dir"
            os.mkdir(path)
            os.chmod(path,0o777)
            _logger.info("Folder %s created"%path)
            self.response['extra-addons'] = path
            return path
        except OSError as e:
            _logger.info("Errro",e)
            raise e
    
    def is_container_available(self,name):
        try:
            self.dclient.containers.get(name)
            return True
        except (docker.errors.ContainerError, docker.errors.ImageNotFound, docker.errors.APIError, Exception) as e:
            _logger.info("Container %s not available")
            return False

    def run_eagle(self,name, db):
        self.response['name'] = name
        try:
            port = self.find_me_an_available_port_within(8000,9000)#find_me_an_available_port()  # Grepping an avialable port.
            if port == False:
                return False
            path = self.mkdir_OdooConfig(name, "eagle.conf") #Mounting the eagle.conf file. Should ask user for the location.Assuming /root/Eagle/config/$name for now.
            self.add_config_paramenter(self.eagle_config+"/"+name+"/eagle-server.conf","dbfilter = %s"%db) 
            self.add_config_paramenter(self.eagle_config+"/"+name+"/eagle-server.conf","db_user = %s"%self.db_user) 
            self.add_config_paramenter(self.eagle_config+"/"+name+"/eagle-server.conf","admin_passwd = %s"%self.container_master) 
            self.add_config_paramenter(self.eagle_config+"/"+name+"/eagle-server.conf","db_host = %s"%self.db_host) 
            self.add_config_paramenter(self.eagle_config+"/"+name+"/eagle-server.conf","db_port = %s"%self.db_port) 
            self.add_config_paramenter(self.eagle_config+"/"+name+"/eagle-server.conf","db_password = %s"%self.db_password) 
            extra_path = self.mkdir_mnt_extra_addons(name)
            self.dclient.containers.run(image=self.eagle_image,name=name,detach=True,volumes={extra_path:{'bind':self.data_dir,"mode":"rw"}, path: {'bind': "/etc/eagle/", 'mode': 'rw'},self.common_addons:{'bind': "/mnt/extra-addons", 'mode': 'rw'}},ports={8069:port},tty=True) #Start the container
            _logger.info("Let's give Eagle 2s")
            time.sleep(2)
            self.response['container_id'] = self.response['name']
            _logger.info("Eagle container with name %s started successfully. Hit http://localhost:%s"%(name,port))
            return port
        except (docker.errors.ContainerError, docker.errors.ImageNotFound, docker.errors.APIError, Exception) as e:
            _logger.info("Eagle container with name %s couldn't be started. Error: %s"%(name,e))
            self.remove_container(name)
            return False
    def add_config_paramenter(self,file_path,value):
        try:
            with open(file_path,"a") as config_file:
                config_file.write(str(value)+"\n")
        except Exception as e:
            _logger.info("Error appneding to file %r",e)
                
    
    def execute_on_shell(self,cmd):
        try:
            res = subprocess.check_output(cmd,stderr=subprocess.STDOUT,shell=True)
            _logger.info("-----------COMMAND RESULT--------%r", res)
            return True
        except Exception as e:
            _logger.info("+++++++++++++ERRROR++++%r",e)
            return False

    def write_saas_data(self,folder,data):
        path = self.eagle_config + "/"+folder 
        _logger.info("Writing data to %r"%path)
        with open(path+"/saas_data.conf",'w') as file:
            file.write("[options]\n")
            for each in data.items():
                file.write("%s = %s\n"%each)

    def cloning_db(self,url,source_db,new_db,admin_passwd):
        sock_db = xmlrpc.client.ServerProxy('{}/xmlrpc/2/db'.format(url))
        count = 0
        while count < 10:
            try:
                if source_db in sock_db.list():
                    result = sock_db.duplicate_database(admin_passwd, source_db, new_db)
                    return result
            except Exception as e:
                _logger.info("Error listing DB: %r"%e)
            count += 1
            time.sleep(5)

        return False

class nginx_vhost:

    def __init__(self,vhostTemplate="vhosttemplate.txt",sitesEnable='/var/lib/eagle/Eagle-SAAS_Data/docker_vhosts/',sitesAvailable='/etc/nginx/sites-available/'):
        self.vhostTemplate=vhostTemplate
        self.sitesEnable=sitesEnable
        self.sitesAvailable=sitesAvailable

    def execute_on_shell(self,cmd):
        try:
            res = subprocess.check_output(cmd,stderr=subprocess.STDOUT,shell=True)
            _logger.info("-----------COMMAND RESULT--------%r", res)
            return True
        except Exception as e:
            _logger.info("+++++++++++++ERRROR++++%r",e)
            return False

    def domainmapping(self,subdomain,backend):
        _logger.info("++++%r   ======== %r++"%(subdomain,backend))
        new_conf = self.sitesEnable+str.lower(subdomain)+".conf"
        subdomain = str.lower(subdomain)
        cmd = "cp %s %s"%((self.sitesAvailable+self.vhostTemplate),new_conf)
        if not self.execute_on_shell(cmd):
            _logger.info("Couldn't Create Vhost file!!")
            return False
        cmd = "sed -i \"s/BACKEND_TO_BE_REPLACED/%s/g\" %s"%(backend,new_conf)
        if not self.execute_on_shell(cmd):
            _logger.info("Couldn't Replace Port!!")
            return False
        cmd = "sed -i \"s/DOMAIN_TO_BE_REPLACED/%s/g\"  %s"%(subdomain,new_conf)
        if not self.execute_on_shell(cmd):
            _logger.info("Couldn't Replace Subdomain!!")
            return False
        if not self.execute_on_shell("sudo nginx -t"):
            _logger.info("Couldn't Replace Subdomain!!")
            return False
        if not self.execute_on_shell("sudo nginx -s reload"):
            _logger.info("Couldn't Replace Subdomain!!")
            return False
        return True 

def main(context=None):
    _logger.info(context)
    db = context.get("db_name")
    db_template = context.get("db_template")
    modules = context.get('modules')
    host_domain = context.get("host_domain")

    OdooObject = eagle_container(db=db,eagle_config=context['config_path'],db_server = context['db_server'], host_server = context['host_server'])
    OdooObject.get_client()

    sitesEnable = OdooObject.eagle_config+"/docker_vhosts/"
    port = OdooObject.run_eagle(host_domain, db)

    if not port:
        return False
    try:
        src = "%s/%s/data-dir/filestore/%s"%(OdooObject.eagle_config,OdooObject.eagle_template,db_template)
        dest = "%s/%s/data-dir/filestore"%(OdooObject.eagle_config,host_domain)
        try:
            os.mkdir(dest)
        except OSError as e:
            _logger.info("Coudlnot create filestore %r",e)
        dest = dest+"/"+db
        _logger.info("SOURCE %r",src)
        _logger.info("DEST %r",dest)
        shutil.copytree(src, dest)
        os.chmod(dest,0o777)
    except OSError as e:
        _logger.info("Filestore couldnot be copied %r",e)
    result = OdooObject.cloning_db("{}:{}".format("http://localhost", port),db_template,db,OdooObject.container_master)
    time.sleep(1)
    _logger.info("Cloning Res %r"%result)
    time.sleep(1)
    result = {'modules_installation': True, 'modules_missed': []}
    OdooObject.response['url'] = "{}:{}".format(str(host_domain), port)
    _logger.info("-----------MAPPING DOMAIN--------")
    NginxVhost = nginx_vhost(sitesAvailable=sitesEnable,sitesEnable=sitesEnable)
    resp = NginxVhost.domainmapping(str(host_domain),"localhost:{}".format(str(port)))
    _logger.info("----------MAPPING RESULT--------%r", resp)
    if resp:
        OdooObject.response['url']  = "http://{}".format(str.lower(host_domain))
    OdooObject.response.update(result)
    _logger.info(OdooObject.response)
    OdooObject.write_saas_data(host_domain, OdooObject.response)
    return OdooObject.response

def create_db_template(db_template=None,modules=None, config_path=None,host_server = None, db_server = None):
    response = {}
    _logger.info(locals())
    OdooObject = eagle_container(db=db_template,eagle_config = config_path, db_server = db_server, host_server = host_server)
    OdooObject.get_client()
    response['eagle_image'] = OdooObject.eagle_image
    sitesEnable = OdooObject.eagle_config+"/docker_vhosts/"
    host_domain = "db13_templates."+host_server['server_domain']
    response['port'] = OdooObject.template_eagle_port
    response['name'] = OdooObject.eagle_template
    if not OdooObject.is_container_available(OdooObject.eagle_template):
        try:
            path = OdooObject.mkdir_OdooConfig(OdooObject.eagle_template,"eagle-template.conf") #Mounting the eagle.conf file. Should ask user for the location.Assuming /root/Eagle/config/$name for now.
            extra_path = OdooObject.mkdir_mnt_extra_addons(OdooObject.eagle_template)
            OdooObject.add_config_paramenter(OdooObject.eagle_config+"/"+OdooObject.eagle_template+"/eagle-server.conf","db_user = %s"%OdooObject.db_user) 
            OdooObject.add_config_paramenter(OdooObject.eagle_config+"/"+OdooObject.eagle_template+"/eagle-server.conf","admin_passwd = %s"%OdooObject.template_master) 
            OdooObject.add_config_paramenter(OdooObject.eagle_config+"/"+OdooObject.eagle_template+"/eagle-server.conf","db_port = %s"%OdooObject.db_port) 
            OdooObject.add_config_paramenter(OdooObject.eagle_config+"/"+OdooObject.eagle_template+"/eagle-server.conf","db_host = %s"%OdooObject.db_host) 
            OdooObject.add_config_paramenter(OdooObject.eagle_config+"/"+OdooObject.eagle_template+"/eagle-server.conf","db_password = %s"%OdooObject.db_password)

            OdooObject.dclient.containers.run(image=OdooObject.eagle_image,name=OdooObject.eagle_template,detach=True,volumes={extra_path:{'bind':OdooObject.data_dir,"mode":"rw"},path: {'bind': "/etc/eagle/", 'mode': 'rw'},OdooObject.common_addons:{'bind': "/mnt/extra-addons", 'mode': 'rw'}},ports={8069:OdooObject.template_eagle_port},tty=True) #Start the container
            _logger.info("Let's give Eagle 2s")
            time.sleep(2)
            NginxVhost = nginx_vhost(sitesAvailable=sitesEnable,sitesEnable=sitesEnable)
            response['nginx_vhost'] = NginxVhost.domainmapping(str(host_domain),"localhost:{}".format(str(OdooObject.template_eagle_port)))
        except (docker.errors.ContainerError, docker.errors.ImageNotFound, docker.errors.APIError, Exception) as e:
            _logger.info("Eagle container with name %s couldn't be started. Error: %s"%(OdooObject.eagle_template,e))

            OdooObject.remove_container(OdooObject.eagle_template)
            response.update({ 'status': False, 'msg': e,})
            return response
    response['container_id'] = response['name']
    if OdooObject.create_db("http://localhost:%s"%OdooObject.template_eagle_port, db_template,OdooObject.template_master): #Creating a default DB.
        _logger.info("Eagle container with name %s started successfully. Hit http://localhost:%s"%(OdooObject.eagle_template,OdooObject.template_eagle_port))
        result = saas_client_db.create_saas_client(operation = "install", eagle_url="http://{}:{}".format("localhost", OdooObject.template_eagle_port), eagle_username = "admin" , eagle_password = "admin", database_name=db_template,modules_list=modules,admin_passwd=OdooObject.template_master)
        response['result'] = result
        response['status'] = True
    else:
        response.update({'status': False,'msg': "Couldn't Create DB. Please try again later or with some other Template Name!",})
    OdooObject.write_saas_data(OdooObject.eagle_template, response)
    return response

