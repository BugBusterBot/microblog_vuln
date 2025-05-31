# Microblog Vuln

## Setup Instructions

## Important Note

This project requires **Python 3.12**, which is available on **Oracle Linux 8.10** or later.  
Please ensure you use Oracle Linux 8.10+ as your OS to install Python 3.12 and meet the project dependencies.

### (Optional) Install Git
If Git is not installed, use the following commands.  
*Note: You may encounter timeouts due to region settings during updates.*

```bash
echo -n "" | sudo tee /etc/yum/vars/ociregion
sudo yum update
sudo dnf install git
```
### Install Python 3.12
```bash
sudo dnf install python3.12
```
### Clone and Setup the Project
```bash
git clone https://github.com/BugBusterBot/microblog_vuln.git
cd microblog_vuln/microblog
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
flask run
