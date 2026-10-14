/* VNCMing scaled framebuffer damage mapping.
 * Distributed under the GNU General Public License, version 2 or later.
 */
#ifndef VNCMING_SCALED_DAMAGE_H
#define VNCMING_SCALED_DAMAGE_H

#include <algorithm>
#include <rfb/Rect.h>

inline rfb::Rect scaledDamage(const rfb::Rect& dirty,
                              int sourceWidth, int sourceHeight,
                              int targetWidth, int targetHeight)
{
  if (dirty.is_empty() || sourceWidth <= 0 || sourceHeight <= 0 ||
      targetWidth <= 0 || targetHeight <= 0)
    return rfb::Rect(0, 0, 0, 0);

  // Bilinear samples also depend on adjacent source pixels. Round the
  // destination bounds outwards, with a pixel for XRender fixed-point rounding.
  int left = std::max(0, dirty.tl.x - 1);
  int top = std::max(0, dirty.tl.y - 1);
  int right = std::min(sourceWidth, dirty.br.x + 1);
  int bottom = std::min(sourceHeight, dirty.br.y + 1);
  return rfb::Rect(
    std::max(0, int((long long)left * targetWidth / sourceWidth) - 1),
    std::max(0, int((long long)top * targetHeight / sourceHeight) - 1),
    std::min(targetWidth, int(((long long)right * targetWidth + sourceWidth - 1) / sourceWidth) + 1),
    std::min(targetHeight, int(((long long)bottom * targetHeight + sourceHeight - 1) / sourceHeight) + 1));
}

#endif
