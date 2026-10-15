/* Copyright 2011 Pierre Ossman <ossman@cendio.se> for Cendio AB
 * 
 * This is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 * 
 * This software is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 * 
 * You should have received a copy of the GNU General Public License
 * along with this software; if not, write to the Free Software
 * Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307,
 * USA.
 */

#ifdef HAVE_CONFIG_H
#include <config.h>
#endif

#include <assert.h>
#include <stdio.h>
#include <string.h>

#include <FL/Fl.H>
#include "MacMotion.h"
#include <FL/fl_ask.H>
#include "StyledMessage.h"
#include <FL/Fl_Window.H>
#include <FL/Fl_Box.H>
#include <FL/Fl_Input.H>
#include <FL/Fl_Secret_Input.H>
#include <FL/Fl_Button.H>
#include <FL/Fl_Return_Button.H>
#include <FL/Fl_Pixmap.H>

#include <rfb/util.h>
#include <rfb/Password.h>
#include <rfb/Exception.h>

#include "i18n.h"
#include "fltk_layout.h"
#include "parameters.h"
#include "UserDialog.h"

/* xpm:s predate const, so they have invalid definitions */
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wwrite-strings"
#include "../media/secure.xpm"
#include "../media/insecure.xpm"
#pragma GCC diagnostic pop

using namespace rfb;

static Fl_Pixmap secure_icon(secure);
static Fl_Pixmap insecure_icon(insecure);

class RememberCredentialsButton : public ModernCheckButton {
public:
  RememberCredentialsButton(int x, int y, int w, int h, const char* label)
    : ModernCheckButton(x,y,w,h,label) {}
  void draw() {
    fl_color(fl_rgb_color(250,249,247)); fl_rectf(x(),y(),w(),h());
    int top=y()+(h()-18)/2;
    macRoundBox(x(),top,18,18,value()?fl_rgb_color(245,128,37):fl_rgb_color(221,216,210));
    if (value()) {
      fl_color(FL_WHITE); fl_line_style(FL_SOLID,2);
      fl_line(x()+4,top+9,x()+8,top+13,x()+14,top+5); fl_line_style(0);
    } else macRoundBox(x()+1,top+1,16,16,FL_WHITE);
    fl_color(labelcolor()); fl_font(labelfont(),labelsize());
    fl_draw(label(),x()+26,y(),w()-26,h(),FL_ALIGN_LEFT);
  }
};

static int ret_val = 0;

static void button_cb(Fl_Widget *widget, void *val) {
  ret_val = (fl_intptr_t)val;
  widget->window()->hide();
}

UserDialog::UserDialog()
{
}

UserDialog::~UserDialog()
{
}

#include <unistd.h>
#include <sys/socket.h>
#include <arpa/inet.h>
#include <errno.h>
#include <string>

static std::string pendingUsername, pendingPassword;
void commitSavedCredentials()
{
  const char* descriptor = getenv("VNCMING_SAVE_CREDENTIALS_FD");
  if (!descriptor) {
    std::fill(pendingPassword.begin(), pendingPassword.end(), '\0');
    pendingPassword.clear(); pendingUsername.clear();
    return;
  }
  int fd = atoi(descriptor);
  unsetenv("VNCMING_SAVE_CREDENTIALS_FD");
  if (fd >= 3 && !pendingPassword.empty()) {
    uint32_t lengths[] = {htonl(pendingUsername.size()), htonl(pendingPassword.size())};
    std::string packet(reinterpret_cast<char*>(lengths), sizeof(lengths));
    packet += pendingUsername; packet += pendingPassword;
    // A private datagram is atomic and cannot raise SIGPIPE if the launcher exits.
    ssize_t sent;
    do { sent=send(fd, packet.data(), packet.size(), MSG_NOSIGNAL); }
    while (sent < 0 && errno == EINTR);
    std::fill(packet.begin(), packet.end(), '\0');
  }
  if (fd >= 3 && pendingPassword.empty()) {
    const char done = 0;
    send(fd, &done, 1, MSG_NOSIGNAL);
  }
  if (fd >= 3) close(fd);
  std::fill(pendingPassword.begin(), pendingPassword.end(), '\0');
  pendingPassword.clear(); pendingUsername.clear();
}

static bool readCredentialBytes(int fd, void *buffer, size_t count)
{
  char *next = static_cast<char*>(buffer);
  while (count) {
    ssize_t n = read(fd, next, count);
    if (n < 0 && errno == EINTR) continue;
    if (n <= 0) return false;
    next += n; count -= n;
  }
  return true;
}

void UserDialog::getUserPasswd(bool secure, char** user, char** password)
{
  std::fill(pendingPassword.begin(), pendingPassword.end(), '\0');
  pendingPassword.clear(); pendingUsername.clear();
  CharArray passwordFileStr(passwordFile.getData());

  assert(password);
  // A private inherited pipe keeps credentials out of argv and environment.
  const char *credentialDescriptor = getenv("VNCMING_CREDENTIALS_FD");
  if (credentialDescriptor) {
    int fd = atoi(credentialDescriptor);
    unsetenv("VNCMING_CREDENTIALS_FD");
    uint32_t lengths[2];
    bool valid = fd >= 3 && readCredentialBytes(fd, lengths, sizeof(lengths));
    uint32_t userLength = valid ? ntohl(lengths[0]) : 0;
    uint32_t passLength = valid ? ntohl(lengths[1]) : 0;
    valid = valid && userLength <= 4096 && passLength > 0 && passLength <= 4096;
    std::string username(valid ? userLength : 0, '\0'), secret(valid ? passLength : 0, '\0');
    if (valid)
      valid = readCredentialBytes(fd, &username[0], userLength) &&
              readCredentialBytes(fd, &secret[0], passLength);
    if (fd >= 3) close(fd);
    if (valid) {
      if (user) *user = strdup(username.c_str());
      *password = strdup(secret.c_str());
      std::fill(secret.begin(), secret.end(), '\0');
      return;
    }
  }
  char *envUsername = getenv("VNC_USERNAME");
  char *envPassword = getenv("VNC_PASSWORD");

  if(user && envUsername && envPassword) {
    *user = strdup(envUsername);
    *password = strdup(envPassword);
    return;
  }

  if (!user && envPassword) {
    *password = strdup(envPassword);
    return;
  }

  if (!user && passwordFileStr.buf[0]) {
    ObfuscatedPasswd obfPwd(256);
    FILE* fp;

    fp = fopen(passwordFileStr.buf, "rb");
    if (!fp)
      throw rfb::Exception(_("Opening password file failed"));

    obfPwd.length = fread(obfPwd.buf, 1, obfPwd.length, fp);
    fclose(fp);

    PlainPasswd passwd(obfPwd);
    *password = passwd.takeBuf();

    return;
  }

  Fl_Window *win;
  Fl_Box *banner;
  Fl_Input *username;
  Fl_Secret_Input *passwd;
  Fl_Button *button;

  int y;

  win = new MotionWindow(460, 300, "身份验证 — VNCMing");
  win->color(fl_rgb_color(250, 249, 247));
  win->callback(button_cb,(void *)0);

  banner = new Fl_Box(24, 18, win->w()-48, 34, "连接到远程桌面");
  banner->box(FL_FLAT_BOX);
  banner->color(fl_rgb_color(250, 249, 247));
  banner->labelcolor(fl_rgb_color(55, 50, 45));
  banner->align(FL_ALIGN_LEFT | FL_ALIGN_INSIDE);
  banner->labelfont(FL_HELVETICA_BOLD);
  banner->labelsize(18);
  y = 68;
  Fl_Box *security = new Fl_Box(24, y, win->w()-48, 30,
      secure ? "此连接已加密" : "此连接未加密");
  security->box(macBox());
  security->color(secure ? fl_rgb_color(235, 246, 240) : fl_rgb_color(255, 244, 225));
  security->labelcolor(secure ? fl_rgb_color(40, 105, 75) : fl_rgb_color(135, 90, 30));
  security->align(FL_ALIGN_CENTER | FL_ALIGN_INSIDE);
  y += 46;
  if (user) {
    (new Fl_Box(24, y, 90, 34, "用户名"))->align(FL_ALIGN_LEFT|FL_ALIGN_INSIDE);
    username = new ModernInput(114, y, win->w()-138, 34);
    username->box(modernInputBox());
    username->color(FL_WHITE);
    y += 50;
  } else {
    username = NULL;
  }
  (new Fl_Box(24, y, 90, 34, "密码"))->align(FL_ALIGN_LEFT|FL_ALIGN_INSIDE);
  passwd = new ModernSecretInput(114, y, win->w()-138, 34);
  passwd->box(modernInputBox());
  passwd->color(FL_WHITE);
  y += 46;
  RememberCredentialsButton* remember = new RememberCredentialsButton(114, y, 322, 28, "保存用户名和密码");
  remember->value(1);
  remember->tooltip("连接成功后保存到系统钥匙环");
  y += 46;

  button = new MacReturnButton(326, y, 110, 34, "连接");
  button->box(macBox());
  button->color(fl_rgb_color(245, 128, 37));
  button->labelcolor(FL_WHITE);
  button->callback(button_cb, (void*)0);
  button = new MacButton(204, y, 110, 34, "取消");
  button->box(macBox());
  button->color(fl_rgb_color(250, 247, 243));
  button->callback(button_cb, (void*)1);
  button->shortcut(FL_Escape);
  y += 54;

  win->end();

  win->size(win->w(), y);

  win->set_modal();

  ret_val = -1;

  win->show();
  if (username) username->take_focus(); else passwd->take_focus();
  while (win->shown()) Fl::wait();

  if (ret_val == 0) {
    if (user)
      *user = strDup(username->value());
    *password = strDup(passwd->value());
    if (remember->value() && strlen(passwd->value()) <= 4096 &&
        (!username || strlen(username->value()) <= 4096)) {
      pendingUsername = username ? username->value() : "";
      pendingPassword = passwd->value();
    }
  }

  delete win;

  if (ret_val != 0)
    throw rfb::Exception(_("Authentication cancelled"));
}

bool UserDialog::showMsgBox(int flags, const char* title, const char* text)
{
  // This host's name mismatch was explicitly approved in the launcher.
  const char* approved = getenv("VNCMING_APPROVED_HOSTNAME");
  if (approved && strcmp(title, "Certificate hostname mismatch") == 0) {
    std::string prefix = std::string("Hostname (") + approved + ")";
    if (strncmp(text, prefix.c_str(), prefix.size()) == 0)
      return true;
  }
  char buffer[1024];

  if (fltk_escape(text, buffer, sizeof(buffer)) >= sizeof(buffer))
    return 0;

  // FLTK doesn't give us a flexible choice of the icon, so we ignore those
  // bits for now.

  vncMessageTitle(title);

  switch (flags & 0xf) {
  case M_OKCANCEL:
    return vncChoice("%s", NULL, fl_ok, fl_cancel, buffer) == 1;
  case M_YESNO:
    return vncChoice("%s", NULL, fl_yes, fl_no, buffer) == 1;
  case M_OK:
  default:
    if (((flags & 0xf0) == M_ICONERROR) ||
        ((flags & 0xf0) == M_ICONWARNING))
      vncAlert("%s", buffer);
    else
      vncMessage("%s", buffer);
    return true;
  }

  return false;
}
