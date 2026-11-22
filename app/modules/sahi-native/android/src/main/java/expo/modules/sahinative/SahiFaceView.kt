package expo.modules.sahinative

import android.content.Context
import android.content.ContextWrapper
import android.graphics.Bitmap
import android.graphics.PixelFormat
import android.os.SystemClock
import android.util.Log
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.core.content.ContextCompat
import androidx.lifecycle.LifecycleOwner
import com.google.mediapipe.framework.image.BitmapImageBuilder
import com.google.mediapipe.framework.image.MPImage
import com.google.mediapipe.tasks.core.BaseOptions
import com.google.mediapipe.tasks.core.Delegate
import com.google.mediapipe.tasks.vision.core.RunningMode
import com.google.mediapipe.tasks.vision.facelandmarker.FaceLandmarker
import com.google.mediapipe.tasks.vision.facelandmarker.FaceLandmarkerResult
import expo.modules.kotlin.AppContext
import expo.modules.kotlin.viewevent.EventDispatcher
import expo.modules.kotlin.views.ExpoView
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors

class SahiFaceView(context: Context, appContext: AppContext) : ExpoView(context, appContext) {
  val onFace by EventDispatcher<Map<String, Any?>>()

  private val previewView = PreviewView(context).apply {
    // TextureView: the default SurfaceView renders black inside RN's clipped, rounded containers.
    implementationMode = PreviewView.ImplementationMode.COMPATIBLE
    scaleType = PreviewView.ScaleType.FILL_CENTER
    layoutParams = LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.MATCH_PARENT)
  }

  private var cameraProvider: ProcessCameraProvider? = null
  private var cameraExecutor: ExecutorService? = null
  @Volatile private var faceLandmarker: FaceLandmarker? = null
  @Volatile private var released = false

  private var active: Boolean = true
  private var lastAnalyzedMs = 0L
  private var lastLandmarkerTimestampMs = 0L
  @Volatile private var latestLuma = 0.0

  init {
    addView(previewView)
  }

  fun setActive(isActive: Boolean) {
    active = isActive
  }

  override fun onLayout(changed: Boolean, left: Int, top: Int, right: Int, bottom: Int) {
    super.onLayout(changed, left, top, right, bottom)
    val width = right - left
    val height = bottom - top
    previewView.layout(0, 0, width, height)
  }

  override fun onAttachedToWindow() {
    super.onAttachedToWindow()
    released = false
    initLandmarkerAndCamera()
  }

  override fun onDetachedFromWindow() {
    super.onDetachedFromWindow()
    releaseResources()
  }

  fun onDestroy() {
    releaseResources()
  }

  private fun releaseResources() {
    released = true

    try {
      cameraProvider?.unbindAll()
      cameraProvider = null
    } catch (e: Exception) {
      Log.e(TAG, "Error unbinding camera", e)
    }

    val landmarker = faceLandmarker
    faceLandmarker = null
    val executor = cameraExecutor
    cameraExecutor = null

    if (executor != null && !executor.isShutdown) {
      if (landmarker != null) {
        try {
          executor.execute {
            try {
              landmarker.close()
            } catch (e: Exception) {
              Log.e(TAG, "Error closing face landmarker on executor", e)
            }
          }
        } catch (e: Exception) {
          Log.e(TAG, "Error submitting landmarker close to executor", e)
          try {
            landmarker.close()
          } catch (closeEx: Exception) {
            Log.e(TAG, "Error closing face landmarker directly", closeEx)
          }
        }
      }
      try {
        executor.shutdown()
      } catch (e: Exception) {
        Log.e(TAG, "Error shutting down camera executor", e)
      }
    } else if (landmarker != null) {
      try {
        landmarker.close()
      } catch (e: Exception) {
        Log.e(TAG, "Error closing face landmarker", e)
      }
    }
  }

  private fun initLandmarkerAndCamera() {
    val executor = if (cameraExecutor == null || cameraExecutor!!.isShutdown) {
      Executors.newSingleThreadExecutor().also { cameraExecutor = it }
    } else {
      cameraExecutor!!
    }

    executor.execute {
      if (released) return@execute
      if (faceLandmarker == null) {
        try {
          val baseOptions = BaseOptions.builder()
            .setModelAssetPath("face_landmarker.task")
            .setDelegate(Delegate.CPU)
            .build()

          val options = FaceLandmarker.FaceLandmarkerOptions.builder()
            .setBaseOptions(baseOptions)
            .setRunningMode(RunningMode.LIVE_STREAM)
            .setNumFaces(1)
            .setOutputFaceBlendshapes(false)
            .setOutputFacialTransformationMatrixes(true)
            .setResultListener { result, inputImage ->
              handleResult(result, inputImage)
            }
            .setErrorListener { error ->
              Log.e(TAG, "FaceLandmarker error: ${error.message}", error)
            }
            .build()

          val created = FaceLandmarker.createFromOptions(context, options)
          if (released) {
            try {
              created.close()
            } catch (e: Exception) {
              Log.e(TAG, "Error closing face landmarker after release", e)
            }
            return@execute
          }
          faceLandmarker = created
          Log.i(TAG, "FaceLandmarker ready")
        } catch (e: Exception) {
          Log.e(TAG, "Failed to initialize FaceLandmarker", e)
        }
      }

      if (released) return@execute

      ContextCompat.getMainExecutor(context).execute {
        if (!released) {
          bindCamera()
        }
      }
    }
  }

  private fun getLifecycleOwner(): LifecycleOwner? {
    var ctx: Context? = context
    while (ctx is ContextWrapper) {
      if (ctx is LifecycleOwner) return ctx
      ctx = ctx.baseContext
    }
    val act = appContext.currentActivity
    if (act is LifecycleOwner) return act
    return null
  }

  private fun bindCamera() {
    if (released) return

    val lifecycleOwner = getLifecycleOwner() ?: run {
      post {
        if (!released) {
          bindCamera()
        }
      }
      return
    }

    val cameraProviderFuture = ProcessCameraProvider.getInstance(context)
    cameraProviderFuture.addListener({
      if (released) return@addListener
      try {
        val provider = cameraProviderFuture.get()
        if (released) return@addListener
        cameraProvider = provider

        val preview = Preview.Builder().build().also {
          it.setSurfaceProvider(previewView.surfaceProvider)
        }

        val analysis = ImageAnalysis.Builder()
          .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
          .setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_RGBA_8888)
          .build()

        val executor = cameraExecutor ?: return@addListener
        analysis.setAnalyzer(executor) { imageProxy ->
          processImageProxy(imageProxy)
        }

        val cameraSelector = CameraSelector.DEFAULT_FRONT_CAMERA

        provider.unbindAll()
        provider.bindToLifecycle(lifecycleOwner, cameraSelector, preview, analysis)
        Log.i(TAG, "camera bound")
      } catch (e: Exception) {
        Log.e(TAG, "Failed to bind CameraX", e)
      }
    }, ContextCompat.getMainExecutor(context))
  }

  private fun processImageProxy(imageProxy: ImageProxy) {
    try {
      if (released || !active) {
        return
      }

      val now = SystemClock.uptimeMillis()
      // Throttle to <= 15 Hz (~66.6 ms)
      if (now - lastAnalyzedMs < 66L) {
        return
      }
      lastAnalyzedMs = now

      val plane = imageProxy.planes[0]
      val isRgba = imageProxy.format == PixelFormat.RGBA_8888 || imageProxy.planes.size == 1
      latestLuma = FaceMetrics.computeLuma(plane.buffer, imageProxy.width, imageProxy.height, isRgba)

      val bitmap = imageProxy.toBitmap()
      val rotationDegrees = imageProxy.imageInfo.rotationDegrees
      val rotatedBitmap = if (rotationDegrees != 0) {
        val rotationMatrix = android.graphics.Matrix().apply {
          postRotate(rotationDegrees.toFloat())
        }
        Bitmap.createBitmap(bitmap, 0, 0, bitmap.width, bitmap.height, rotationMatrix, true)
      } else {
        bitmap
      }

      val mpImage = BitmapImageBuilder(rotatedBitmap).build()
      val landmarker = faceLandmarker
      if (landmarker != null) {
        val timestampMs = if (now <= lastLandmarkerTimestampMs) lastLandmarkerTimestampMs + 1 else now
        lastLandmarkerTimestampMs = timestampMs
        landmarker.detectAsync(mpImage, timestampMs)
      }
    } catch (e: Exception) {
      Log.e(TAG, "processImageProxy error", e)
    } finally {
      imageProxy.close()
    }
  }

  private var resultCount = 0

  private fun handleResult(result: FaceLandmarkerResult, inputImage: MPImage) {
    if (resultCount++ % 60 == 0) Log.i(TAG, "result #$resultCount faces=${result.faceLandmarks().size} luma=$latestLuma")
    val landmarksList = result.faceLandmarks()
    if (landmarksList.isEmpty()) {
      emitSample(
        faceFound = false,
        ear = null,
        earLeft = null,
        earRight = null,
        earValid = false,
        yaw = null,
        pitch = null,
        faceBoxFraction = 0.0,
        luma = latestLuma
      )
      return
    }

    val landmarks = landmarksList[0]
    val width = inputImage.width
    val height = inputImage.height

    var minY = Float.MAX_VALUE
    var maxY = -Float.MAX_VALUE
    for (lm in landmarks) {
      val y = lm.y()
      if (y < minY) minY = y
      if (y > maxY) maxY = y
    }
    val faceBoxFraction = (maxY - minY).toDouble().coerceIn(0.0, 1.0)

    val pts = Array(landmarks.size) { i ->
      doubleArrayOf(
        landmarks[i].x().toDouble() * width,
        landmarks[i].y().toDouble() * height
      )
    }

    val earRight = FaceMetrics.eyeAspectRatio(pts, FaceMetrics.RIGHT_EYE_EAR)
    val earLeft = FaceMetrics.eyeAspectRatio(pts, FaceMetrics.LEFT_EYE_EAR)
    val combinedEar = FaceMetrics.combineEar(earRight, earLeft)

    val matrixesOpt = result.facialTransformationMatrixes()
    val headPose = if (matrixesOpt.isPresent && matrixesOpt.get().isNotEmpty()) {
      FaceMetrics.headPoseFromMatrix(matrixesOpt.get()[0])
    } else {
      null
    }

    val yaw = headPose?.yaw
    val pitch = headPose?.pitch

    val earValid = FaceMetrics.isEarValid(yaw, pitch, combinedEar)
    val ear = if (earValid) combinedEar else null

    emitSample(
      faceFound = true,
      ear = ear,
      earLeft = earLeft,
      earRight = earRight,
      earValid = earValid,
      yaw = yaw,
      pitch = pitch,
      faceBoxFraction = faceBoxFraction,
      luma = latestLuma
    )
  }

  private fun emitSample(
    faceFound: Boolean,
    ear: Double?,
    earLeft: Double?,
    earRight: Double?,
    earValid: Boolean,
    yaw: Double?,
    pitch: Double?,
    faceBoxFraction: Double,
    luma: Double
  ) {
    val payload: Map<String, Any?> = mapOf(
      "faceFound" to faceFound,
      "ear" to ear,
      "earLeft" to earLeft,
      "earRight" to earRight,
      "earValid" to earValid,
      "yaw" to yaw,
      "pitch" to pitch,
      "faceBoxFraction" to faceBoxFraction,
      "luma" to luma,
      "t" to System.currentTimeMillis().toDouble()
    )
    post {
      onFace(payload)
    }
  }

  companion object {
    private const val TAG = "SahiFaceView"
  }
}
