# Alternative Nitrokey Application - nitropy-app2

Work in Progress !!

## To run on Linux:
```
git clone https://github.com/nitrokey/nitropy-app2.git
cd nitropy-app2
make
source venv/bin/activate
python3 nitropyapp/gui.py
```
## Notes:
* the current version uses pynitrokey 
* therefore python >3.9 must first be installed
* pynitrokey version used https://github.com/Nitrokey/pynitrokey/tree/nk3-updater

## To run on Windows: 
```
python3 -m venv venv
venv/Scripts/python -m pip install -U pip
git installed and path?
venv/Scripts/python -m pip install -U -r dev-requirements.txt
venv/Scripts/python -m flit install --symlink
venv/Scripts/python -m pip install pywin32
venv/Scripts/python venv/Scripts/pywin32_postinstall.py -install
venv/Scripts/activate
python nitropyapp/gui.py
```
