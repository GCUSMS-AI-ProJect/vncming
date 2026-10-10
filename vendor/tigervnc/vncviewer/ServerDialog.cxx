/* Copyright 2011 Pierre Ossman <ossman@cendio.se> for Cendio AB
 * Copyright 2012 Samuel Mannehed <samuel@cendio.se> for Cendio AB
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

#include <errno.h>
#include <algorithm>

#include <FL/Fl.H>
#include <FL/Fl_Input.H>
#include <FL/Fl_Input_Choice.H>
#include <FL/Fl_Button.H>
#include <FL/Fl_Return_Button.H>
#include <FL/fl_draw.H>
#include <FL/fl_ask.H>
#include "StyledMessage.h"
#include <FL/Fl_Box.H>
#include <FL/Fl_Native_File_Chooser.H>

#include <os/os.h>
#include <rfb/Exception.h>
#include <rfb/LogWriter.h>

#include "ServerDialog.h"
#include "OptionsDialog.h"
#include "fltk_layout.h"
#include "i18n.h"
#include "vncviewer.h"
#include "parameters.h"


using namespace std;
using namespace rfb;

static LogWriter vlog("ServerDialog");

const char* SERVER_HISTORY="tigervnc.history";

ServerDialog::ServerDialog()
  : MotionWindow(450, 190, "新建连接 — VNCMing")
{
  color(fl_rgb_color(250,249,247));
  int x, y;
  Fl_Button *button;
  Fl_Box *divider;

  int margin = 20;
  int server_label_width = gui_str_len("IP地址");

  x = margin + server_label_width;
  y = margin;
  
  serverName = new Fl_Input_Choice(x, y, w() - margin*2 - server_label_width, INPUT_HEIGHT, "IP地址");

  serverName->input()->box(modernInputBox());
  serverName->input()->color(FL_WHITE);
  serverName->menubutton()->box(modernPanelBox());
  serverName->menubutton()->color(FL_WHITE);
  int adjust = (w() - 20) / 4;
  int button_width = adjust - margin/2;

  x = margin;
  y = margin + margin/2 + INPUT_HEIGHT;

  y += margin/2;

  button = new MacButton(x, y, button_width, BUTTON_HEIGHT, _("Options..."));
  button->callback(this->handleOptions, this);
  
  x += adjust;
  
  button = new MacButton(x, y, button_width, BUTTON_HEIGHT, _("Load..."));
  button->callback(this->handleLoad, this);

  x += adjust;

  button = new MacButton(x, y, button_width, BUTTON_HEIGHT, _("Save As..."));
  button->callback(this->handleSaveAs, this);
  
  x = 0;
  y += margin/2 + BUTTON_HEIGHT;

  divider = new Fl_Box(x, y, w(), 2);
  divider->box(FL_FLAT_BOX);
  divider->color(fl_rgb_color(225,220,214));
  
  x += margin;
  y += margin/2;

  button = new MacButton(x, y, button_width, BUTTON_HEIGHT, _("About..."));
  button->callback(this->handleAbout, this);

  x = w() - margin - adjust - button_width - 20;

  button = new MacButton(x, y, button_width, BUTTON_HEIGHT, _("Cancel"));
  button->callback(this->handleCancel, this);

  x += adjust;

  button = new MacReturnButton(x, y, button_width+20, BUTTON_HEIGHT, _("Connect"));
  button->color(fl_rgb_color(245,128,37));
  button->labelcolor(FL_WHITE);
  button->callback(this->handleConnect, this);

  callback(this->handleCancel, this);
}


ServerDialog::~ServerDialog()
{
}


void ServerDialog::run(const char* servername, char *newservername)
{
  ServerDialog dialog;

  dialog.serverName->value(servername);

  dialog.show();

  try {
    size_t i;

    dialog.loadServerHistory();

    dialog.serverName->clear();
    for(i = 0; i < dialog.serverHistory.size(); ++i)
      dialog.serverName->add(dialog.serverHistory[i].c_str());
  } catch (Exception& e) {
    vlog.error("%s", e.str());
    vncAlert(_("Unable to load the server history:\n\n%s"),
             e.str());
  }

  while (dialog.shown()) Fl::wait();

  if (dialog.serverName->value() == NULL) {
    newservername[0] = '\0';
    return;
  }

  strncpy(newservername, dialog.serverName->value(), VNCSERVERNAMELEN);
  newservername[VNCSERVERNAMELEN - 1] = '\0';
}

void ServerDialog::handleOptions(Fl_Widget *widget, void *data)
{
  OptionsDialog::showDialog();
}


void ServerDialog::handleLoad(Fl_Widget *widget, void *data)
{
  ServerDialog *dialog = (ServerDialog*)data;
  Fl_Native_File_Chooser file_chooser;
  file_chooser.type(Fl_Native_File_Chooser::BROWSE_FILE);
  file_chooser.title("打开 VNCMing 配置");
  file_chooser.filter("VNC 配置\t*.tigervnc");
  if (file_chooser.show() != 0) return;
  const char* filename = file_chooser.filename();

  try {
    dialog->serverName->value(loadViewerParameters(filename));
  } catch (Exception& e) {
    vlog.error("%s", e.str());
    vncAlert(_("Unable to load the specified configuration file:\n\n%s"),
             e.str());
  }

}


void ServerDialog::handleSaveAs(Fl_Widget *widget, void *data)
{ 
  ServerDialog *dialog = (ServerDialog*)data;
  const char* servername = dialog->serverName->value();
  const char* filename;

  Fl_Native_File_Chooser file_chooser;
  file_chooser.type(Fl_Native_File_Chooser::BROWSE_SAVE_FILE);
  file_chooser.title("保存 VNCMing 配置");
  file_chooser.filter("VNC 配置\t*.tigervnc");
  file_chooser.options(Fl_Native_File_Chooser::SAVEAS_CONFIRM);
  if (file_chooser.show() != 0) return;
  filename = file_chooser.filename();

  try {
    saveViewerParameters(filename, servername);
  } catch (Exception& e) {
    vlog.error("%s", e.str());
    vncAlert(_("Unable to save the specified configuration "
               "file:\n\n%s"), e.str());
  }
  
}


void ServerDialog::handleAbout(Fl_Widget *widget, void *data)
{
  about_vncviewer();
}


void ServerDialog::handleCancel(Fl_Widget *widget, void *data)
{
  ServerDialog *dialog = (ServerDialog*)data;

  dialog->serverName->value("");
  dialog->hide();
}


void ServerDialog::handleConnect(Fl_Widget *widget, void *data)
{
  ServerDialog *dialog = (ServerDialog*)data;
  const char* servername = dialog->serverName->value();

  dialog->hide();

  try {
    saveViewerParameters(NULL, servername);
  } catch (Exception& e) {
    vlog.error("%s", e.str());
    vncAlert(_("Unable to save the default configuration:\n\n%s"),
             e.str());
  }

  try {
    vector<string>::iterator elem = std::find(dialog->serverHistory.begin(), dialog->serverHistory.end(), servername);
    // avoid duplicates in the history
    if(dialog->serverHistory.end() == elem) {
      dialog->serverHistory.insert(dialog->serverHistory.begin(), servername);
      dialog->saveServerHistory();
    }
  } catch (Exception& e) {
    vlog.error("%s", e.str());
    vncAlert(_("Unable to save the server history:\n\n%s"),
             e.str());
  }
}


void ServerDialog::loadServerHistory()
{
  serverHistory.clear();

#ifdef _WIN32
  loadHistoryFromRegKey(serverHistory);
  return;
#endif

  char* homeDir = NULL;
  if (getvnchomedir(&homeDir) == -1)
    throw Exception(_("Could not obtain the home directory path"));

  char filepath[PATH_MAX];
  snprintf(filepath, sizeof(filepath), "%s%s", homeDir, SERVER_HISTORY);
  delete[] homeDir;

  /* Read server history from file */
  FILE* f = fopen(filepath, "r");
  if (!f) {
    if (errno == ENOENT) {
      // no history file
      return;
    }
    throw Exception(_("Could not open \"%s\": %s"),
                    filepath, strerror(errno));
  }

  int lineNr = 0;
  while (!feof(f)) {
    char line[256];

    // Read the next line
    lineNr++;
    if (!fgets(line, sizeof(line), f)) {
      if (feof(f))
        break;

      fclose(f);
      throw Exception(_("Failed to read line %d in file %s: %s"),
                      lineNr, filepath, strerror(errno));
    }

    if (strlen(line) == (sizeof(line) - 1)) {
      fclose(f);
      throw Exception(_("Failed to read line %d in file %s: %s"),
                      lineNr, filepath, _("Line too long"));
    }

    int len = strlen(line);
    if (line[len-1] == '\n') {
      line[len-1] = '\0';
      len--;
    }
    if (line[len-1] == '\r') {
      line[len-1] = '\0';
      len--;
    }

    serverHistory.push_back(line);
  }

  fclose(f);
}

void ServerDialog::saveServerHistory()
{
#ifdef _WIN32
  saveHistoryToRegKey(serverHistory);
  return;
#endif

  char* homeDir = NULL;
  if (getvnchomedir(&homeDir) == -1)
    throw Exception(_("Could not obtain the home directory path"));

  char filepath[PATH_MAX];
  snprintf(filepath, sizeof(filepath), "%s%s", homeDir, SERVER_HISTORY);
  delete[] homeDir;

  /* Write server history to file */
  FILE* f = fopen(filepath, "w+");
  if (!f)
    throw Exception(_("Could not open \"%s\": %s"),
                    filepath, strerror(errno));

  // Save the last X elements to the config file.
  for(size_t i=0; i < serverHistory.size() && i <= SERVER_HISTORY_SIZE; i++)
    fprintf(f, "%s\n", serverHistory[i].c_str());

  fclose(f);
}
