# Installing Debian 13

This guide explains how to install **Debian 13 (Trixie)** on your system.

---

## 1. Download Debian 13 ISO

1. Go to the official Debian website: [https://www.debian.org/CD/http-ftp/](https://www.debian.org/CD/http-ftp/)
2. Choose **Debian 13 ISO**:
   - For most users, the **amd64 (64-bit) netinst** image is recommended.
3. Download the ISO file to your computer.

---

## 2. Create a Bootable USB

You need a USB drive (≥4GB).  

### On Windows:

- Use **Rufus** ([https://rufus.ie](https://rufus.ie))  
  1. Select your USB drive.
  2. Select the Debian 13 ISO.
  3. Click **Start** and wait until the process completes.

### On Linux:

```bash
sudo dd if=/path/to/debian-13.iso of=/dev/sdX bs=4M status=progress && sync
```

---

## 3. Boot from USB

1. Insert the bootable USB into your system.
2. Restart your computer and enter the BIOS/UEFI menu (usually pressing `F2`, `F12`, `Esc`, or `Del` during boot).
3. Set the USB drive as the first boot device.
4. Save changes and exit BIOS/UEFI. Your system will boot from the USB.

---

## 4. Install Debian 13

1. Select **Graphical Install** or **Install**.
2. Choose your language, location, and keyboard layout.
3. Configure network settings.
4. Set up users and passwords.
5. Partition disks (manual or guided).
6. Select software to install (desktop environment recommended).
7. Install the GRUB bootloader when prompted.
8. Finish the installation and reboot.

---

## 5. Post-Installation

1. Remove the USB drive.
2. Boot into your new Debian 13 system.
3. Update the system:

```bash
sudo apt update && sudo apt upgrade -y
```

4. Install additional software as needed.
