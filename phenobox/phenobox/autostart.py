import os
import sys
import time

from config import config
from phenobox import Phenobox

os.chdir(sys.path[0])
config.load_config('{}/{}'.format('config', 'production_config.ini'))
while not os.path.ismount(getattr(config, 'cfg').get('box', 'shared_folder_mountpoint')):
    time.sleep(1)

phenobox = Phenobox()
phenobox.run()
