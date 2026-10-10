#ifndef VNCMING_STYLED_MESSAGE_H
#define VNCMING_STYLED_MESSAGE_H

#include "MacMotion.h"
#include <FL/Fl_Box.H>
#include <FL/fl_ask.H>
#include <cstdarg>
#include <cstdio>
#include <string>
#include <vector>

inline std::string& vncMessageTitleStorage() {
  static std::string title;
  return title;
}
inline void vncMessageTitle(const char* title) {
  vncMessageTitleStorage() = title ? title : "";
}
inline std::string vncFormatMessage(const char* format, va_list args) {
  va_list copy;
  va_copy(copy, args);
  int size = vsnprintf(NULL, 0, format, copy);
  va_end(copy);
  if (size < 0) return format;
  std::vector<char> text(size + 1);
  vsnprintf(text.data(), text.size(), format, args);
  return std::string(text.data());
}
struct VncMessageResult { int value; };
struct VncMessageAction { VncMessageResult* result; int index; };
inline void vncMessageButton(Fl_Widget* widget, void* context) {
  VncMessageAction* action = static_cast<VncMessageAction*>(context);
  action->result->value = action->index;
  widget->window()->hide();
}
inline int vncShowMessage(const std::string& text, bool warning,
                          const char* b0, const char* b1, const char* b2) {
  std::string title = vncMessageTitleStorage();
  vncMessageTitleStorage().clear();
  if (title.empty()) title = warning ? "连接错误 — VNCMing" : "VNCMing";
  const int width = 640;
  int textWidth = width - 48, textHeight = 0;
  fl_font(FL_HELVETICA, 14);
  fl_measure(text.c_str(), textWidth, textHeight, 0);
  int bodyHeight = std::max(64, textHeight + 12);
  MotionWindow window(width, bodyHeight + 168, title.c_str());
  window.color(fl_rgb_color(250, 249, 247));
  window.set_modal();
  VncMessageResult result = {-1};
  VncMessageAction actions[] = {{&result, 0}, {&result, 1}, {&result, 2}};
  window.callback([](Fl_Widget* w, void*) { w->hide(); });
  Fl_Box* symbol = new Fl_Box(24, 22, 40, 40, warning ? "!" : "i");
  symbol->box(macBox());
  symbol->color(fl_rgb_color(255, 232, 212));
  symbol->labelcolor(fl_rgb_color(164, 77, 20));
  symbol->labelfont(FL_HELVETICA_BOLD);
  symbol->labelsize(24);
  Fl_Box* heading = new Fl_Box(80, 22, width - 104, 40, title.c_str());
  heading->align(FL_ALIGN_LEFT | FL_ALIGN_INSIDE | FL_ALIGN_WRAP);
  heading->labelfont(FL_HELVETICA_BOLD);
  heading->labelsize(18);
  heading->labelcolor(fl_rgb_color(55, 50, 45));
  Fl_Box* body = new Fl_Box(24, 82, width - 48, bodyHeight, text.c_str());
  body->align(FL_ALIGN_LEFT | FL_ALIGN_TOP | FL_ALIGN_INSIDE | FL_ALIGN_WRAP);
  body->labelsize(14);
  body->labelcolor(fl_rgb_color(81, 74, 67));
  const char* labels[] = {b0, b1, b2};
  int buttonWidths[3] = {0, 0, 0}, total = 0, count = 0;
  for (int i = 0; i < 3; ++i) {
    if (!labels[i]) continue;
    buttonWidths[i] = std::max(100, static_cast<int>(fl_width(labels[i])) + 36);
    total += buttonWidths[i];
    ++count;
  }
  total += std::max(0, count - 1) * 10;
  int x = width - 24 - total;
  for (int i = 0; i < 3; ++i) {
    if (!labels[i]) continue;
    bool primary = i == (b1 ? 1 : 0);
    Fl_Button* button = primary
      ? static_cast<Fl_Button*>(new MacReturnButton(x, bodyHeight + 110, buttonWidths[i], 38, labels[i]))
      : static_cast<Fl_Button*>(new MacButton(x, bodyHeight + 110, buttonWidths[i], 38, labels[i]));
    button->color(primary ? fl_rgb_color(245, 128, 37) : FL_WHITE);
    button->labelcolor(primary ? FL_WHITE : fl_rgb_color(81, 74, 67));
    button->labelsize(14);
    button->callback(vncMessageButton, &actions[i]);
    x += buttonWidths[i] + 10;
  }
  window.end();
  window.show();
  while (window.shown()) {
    if (Fl::wait() < 0) { window.hide(); break; }
  }
  return result.value;
}
inline void vncAlert(const char* format, ...) {
  va_list args; va_start(args, format);
  std::string text = vncFormatMessage(format, args); va_end(args);
  vncShowMessage(text, true, "确定", NULL, NULL);
}
inline void vncMessage(const char* format, ...) {
  va_list args; va_start(args, format);
  std::string text = vncFormatMessage(format, args); va_end(args);
  vncShowMessage(text, false, "确定", NULL, NULL);
}
inline int vncChoice(const char* format, const char* b0, const char* b1,
                     const char* b2, ...) {
  va_list args; va_start(args, b2);
  std::string text = vncFormatMessage(format, args); va_end(args);
  return vncShowMessage(text, true, b0, b1, b2);
}
#endif
