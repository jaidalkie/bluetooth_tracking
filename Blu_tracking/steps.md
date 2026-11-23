// start ssh agent // run as administrator
Set-Service ssh-agent -StartupType Manual
Start-Service ssh-agent
// as normal powershell
ssh-add $env:USERPROFILE\.ssh\id_ed25519_new
// for each pi

// when pi debian is setup, install

sudo apt update
sudo pip3 install scapy numpy scipy flask --break-system-packages
sudo apt install libopenblas0

// run 

sudo systemctl stop bluetooth
sudo rfkill unblock bluetooth
sudo hciconfig hci0 up
hciconfig
python3 /bt_full

http://192.*********:5000