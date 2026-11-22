package expo.modules.sahinative

import java.nio.ByteBuffer

/**
 * Pure mathematical functions for facial geometry and metrics.
 * Exact port of models/face/src/dms_face/metrics.py and headpose.py.
 */
object FaceMetrics {
  val RIGHT_EYE_EAR = intArrayOf(33, 160, 158, 133, 153, 144)
  val LEFT_EYE_EAR = intArrayOf(362, 385, 387, 263, 373, 380)

  const val MAX_YAW_FOR_EAR_DEG = 30.0
  const val MAX_PITCH_FOR_EAR_DEG = 25.0

  private fun dist(x1: Double, y1: Double, x2: Double, y2: Double): Double {
    return Math.hypot(x1 - x2, y1 - y2)
  }

  /**
   * Convert normalized landmark coordinates to frame pixel coordinates.
   */
  fun toPixels(landmarks: List<Pair<Float, Float>>, width: Int, height: Int): Array<DoubleArray> {
    return Array(landmarks.size) { i ->
      val (x, y) = landmarks[i]
      doubleArrayOf(x.toDouble() * width, y.toDouble() * height)
    }
  }

  /**
   * Eye Aspect Ratio (EAR) = (||p2-p6|| + ||p3-p5||) / (2 * ||p1-p4||)
   * Soukupova & Cech, CVWW 2016.
   * Returns null if horizontal distance < 1e-6.
   */
  fun eyeAspectRatio(pts: Array<DoubleArray>, idx: IntArray): Double? {
    if (idx.size != 6) return null
    for (i in idx) {
      if (i < 0 || i >= pts.size) return null
    }
    val p1 = pts[idx[0]]
    val p2 = pts[idx[1]]
    val p3 = pts[idx[2]]
    val p4 = pts[idx[3]]
    val p5 = pts[idx[4]]
    val p6 = pts[idx[5]]

    val horizontal = dist(p1[0], p1[1], p4[0], p4[1])
    if (horizontal < 1e-6) return null

    val v1 = dist(p2[0], p2[1], p6[0], p6[1])
    val v2 = dist(p3[0], p3[1], p5[0], p5[1])
    return (v1 + v2) / (2.0 * horizontal)
  }

  /**
   * Mean of both eyes when both valid, else whichever is valid (never min).
   */
  fun combineEar(right: Double?, left: Double?): Double? {
    if (right != null && left != null) {
      return (right + left) / 2.0
    }
    return right ?: left
  }

  /**
   * EAR is marked invalid when:
   * - ear is null
   * - |yaw| > 30 deg
   * - |pitch| > 25 deg
   */
  fun isEarValid(yaw: Double?, pitch: Double?, ear: Double?): Boolean {
    if (ear == null) return false
    val y = yaw ?: 0.0
    val p = pitch ?: 0.0
    return Math.abs(y) <= MAX_YAW_FOR_EAR_DEG && Math.abs(p) <= MAX_PITCH_FOR_EAR_DEG
  }

  data class HeadAngles(val yaw: Double, val pitch: Double, val roll: Double)

  /**
   * Head pose (yaw, pitch, roll) in degrees from 4x4 column-major transformation matrix.
   * MediaPipe stores facial transformation matrixes in column-major order: matrix[col * 4 + row].
   */
  fun headPoseFromMatrix(matrix: FloatArray): HeadAngles? {
    if (matrix.size < 16) return null

    // 3x3 rotation matrix, column-major: matrix[col * 4 + row]
    val rmat = Array(3) { r ->
      DoubleArray(3) { c ->
        matrix[c * 4 + r].toDouble()
      }
    }

    // Strip scale: normalize each column
    for (c in 0..2) {
      val norm = Math.sqrt(rmat[0][c] * rmat[0][c] + rmat[1][c] * rmat[1][c] + rmat[2][c] * rmat[2][c])
      if (norm > 1e-9) {
        rmat[0][c] /= norm
        rmat[1][c] /= norm
        rmat[2][c] /= norm
      }
    }

    // Decompose rotation
    val sy = Math.sqrt(rmat[0][0] * rmat[0][0] + rmat[1][0] * rmat[1][0])
    val yaw: Double
    val pitch: Double
    val roll: Double
    if (sy > 1e-6) {
      yaw = Math.atan2(-rmat[2][0], sy)
      pitch = Math.atan2(rmat[2][1], rmat[2][2])
      roll = Math.atan2(rmat[1][0], rmat[0][0])
    } else {
      yaw = Math.atan2(-rmat[2][0], sy)
      pitch = Math.atan2(-rmat[1][2], rmat[1][1])
      roll = 0.0
    }

    val (nYaw, nPitch, nRoll) = normaliseAngles(
      Math.toDegrees(yaw),
      Math.toDegrees(pitch),
      Math.toDegrees(roll)
    )
    return HeadAngles(nYaw, nPitch, nRoll)
  }

  fun normaliseAngles(yaw: Double, pitch: Double, roll: Double): Triple<Double, Double, Double> {
    fun wrap(a: Double): Double {
      var x = a
      while (x > 180.0) x -= 360.0
      while (x < -180.0) x += 360.0
      return x
    }
    var y = wrap(yaw)
    var p = wrap(pitch)
    var r = wrap(roll)

    if (Math.abs(p) > 90.0) {
      p = if (p > 0) wrap(180.0 - p) else wrap(-180.0 - p)
    }
    if (Math.abs(r) > 90.0) {
      r = if (r > 0) wrap(r - 180.0) else wrap(r + 180.0)
    }
    return Triple(y, p, r)
  }

  /**
   * Subsamples frame buffer to cheaply calculate mean luminance (0..255).
   */
  fun computeLuma(buffer: ByteBuffer, width: Int, height: Int, isRgba: Boolean): Double {
    buffer.rewind()
    val totalBytes = buffer.remaining()
    if (totalBytes == 0) return 0.0

    var sum = 0.0
    var count = 0
    if (isRgba) {
      val step = 64 // Subsample every 16 pixels
      var pos = 0
      while (pos + 3 < totalBytes) {
        val r = buffer.get(pos).toInt() and 0xFF
        val g = buffer.get(pos + 1).toInt() and 0xFF
        val b = buffer.get(pos + 2).toInt() and 0xFF
        sum += 0.299 * r + 0.587 * g + 0.114 * b
        count++
        pos += step
      }
    } else {
      val step = 16 // Subsample every 16 Y bytes
      var pos = 0
      while (pos < totalBytes) {
        val y = buffer.get(pos).toInt() and 0xFF
        sum += y
        count++
        pos += step
      }
    }
    return if (count > 0) sum / count else 0.0
  }
}
