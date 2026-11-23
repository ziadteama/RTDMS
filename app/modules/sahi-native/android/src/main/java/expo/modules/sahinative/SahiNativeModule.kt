package expo.modules.sahinative

import android.Manifest
import android.app.Activity
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.media.AudioAttributes
import android.media.RingtoneManager
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import android.net.Uri
import android.net.wifi.WifiNetworkSpecifier
import android.os.Build
import android.os.Handler
import android.os.HandlerThread
import android.os.SystemClock
import android.telephony.SmsManager
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import expo.modules.kotlin.Promise
import expo.modules.kotlin.exception.CodedException
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition

/**
 * Android-only pieces Sahi cannot get from Expo modules:
 *  - SMS + phone call without a user tap (emergency flow; needs SEND_SMS / CALL_PHONE)
 *  - alert notifications without expo-notifications (which bundles Firebase Messaging)
 *  - accelerometer + gyroscope that keep running in the background (expo-sensors stops its
 *    listeners on onHostPause); samples go to JS in batches, the crash detector stays in TS
 *  - joining the Pi hotspot and binding the process to it (it has no internet, so Android would
 *    otherwise route requests for 10.42.0.1 over mobile data)
 */
class SahiNativeModule : Module() {
  private val context: Context
    get() = appContext.reactContext ?: throw CodedException("ERR_NO_CONTEXT", "React context is not available", null)

  private var sensorThread: HandlerThread? = null
  private var motionListener: SensorEventListener? = null
  private var wifiCallback: ConnectivityManager.NetworkCallback? = null
  private var smsReceiver: BroadcastReceiver? = null
  private var smsRequestCode = 1000

  override fun definition() = ModuleDefinition {
    Name("SahiNative")

    Events("onMotion", "onSmsStatus")

    Function("hasTelephony") {
      context.packageManager.hasSystemFeature(PackageManager.FEATURE_TELEPHONY)
    }

    AsyncFunction("sendSms") { numbers: List<String>, text: String ->
      require(Manifest.permission.SEND_SMS)
      ensureSmsReceiver()
      val sms = if (Build.VERSION.SDK_INT >= 31) context.getSystemService(SmsManager::class.java)
      else @Suppress("DEPRECATION") SmsManager.getDefault()
      val parts = sms.divideMessage(text)
      var sent = 0
      val flags = if (Build.VERSION.SDK_INT >= 31) PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_MUTABLE
      else PendingIntent.FLAG_UPDATE_CURRENT
      for (n in numbers) {
        try {
          val sentIntents = ArrayList<PendingIntent>(parts.size)
          val deliveryIntents = ArrayList<PendingIntent>(parts.size)
          for (i in parts.indices) {
            val sIntent = PendingIntent.getBroadcast(
              context, smsRequestCode++,
              Intent(ACTION_SMS_SENT).apply {
                setPackage(context.packageName)
                putExtra("phone", n)
              },
              flags
            )
            val dIntent = PendingIntent.getBroadcast(
              context, smsRequestCode++,
              Intent(ACTION_SMS_DELIVERED).apply {
                setPackage(context.packageName)
                putExtra("phone", n)
              },
              flags
            )
            sentIntents.add(sIntent)
            deliveryIntents.add(dIntent)
          }
          sms.sendMultipartTextMessage(n, null, parts, sentIntents, deliveryIntents)
          sent++
        } catch (_: Exception) {
          sendEvent("onSmsStatus", mapOf("phone" to n, "status" to "failed"))
        }
      }
      sent
    }

    AsyncFunction("call") { number: String ->
      require(Manifest.permission.CALL_PHONE)
      val intent = Intent(Intent.ACTION_CALL, Uri.parse("tel:" + Uri.encode(number)))
      intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
      context.startActivity(intent)
    }

    Function("notify") { id: Int, channel: String, title: String, body: String, url: String? ->
      ensureChannels()
      val launch = context.packageManager.getLaunchIntentForPackage(context.packageName)
        ?: Intent(Intent.ACTION_MAIN)
      if (url != null) {
        launch.action = Intent.ACTION_VIEW
        launch.data = Uri.parse(url)
      }
      launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
      val pending = PendingIntent.getActivity(
        context, id, launch, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
      )
      val sos = channel == CHANNEL_SOS
      // Map legacy "alerts" JS id onto alerts_v2 (sound-enabled channel).
      val channelId = when {
        sos -> CHANNEL_SOS
        channel == "alerts" || channel == CHANNEL_ALERTS -> CHANNEL_ALERTS
        else -> channel
      }
      val n = NotificationCompat.Builder(context, channelId)
        .setSmallIcon(android.R.drawable.ic_dialog_alert)
        .setContentTitle(title)
        .setContentText(body)
        .setPriority(NotificationCompat.PRIORITY_MAX)
        .setCategory(if (sos) NotificationCompat.CATEGORY_ALARM else NotificationCompat.CATEGORY_NAVIGATION)
        .setContentIntent(pending)
        .setAutoCancel(true)
        .setOnlyAlertOnce(!sos)
      if (sos) n.setFullScreenIntent(pending, true)
      if (ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED ||
        Build.VERSION.SDK_INT < 33
      ) {
        notificationManager().notify(id, n.build())
      }
    }

    Function("cancel") { id: Int ->
      notificationManager().cancel(id)
    }

    Function("startMotion") { hz: Int ->
      startMotion(hz)
    }

    Function("stopMotion") {
      stopMotion()
    }

    AsyncFunction("joinWifi") { ssid: String, password: String, promise: Promise ->
      joinWifi(ssid, password, promise)
    }

    Function("unbindNetwork") {
      val cm = context.getSystemService(ConnectivityManager::class.java)
      cm.bindProcessToNetwork(null)
      wifiCallback?.let { runCatching { cm.unregisterNetworkCallback(it) } }
      wifiCallback = null
    }

    View(SahiFaceView::class) {
      Events("onFace")

      Prop("active") { view: SahiFaceView, active: Boolean ->
        view.setActive(active)
      }

      OnViewDestroys { view: SahiFaceView ->
        view.onDestroy()
      }
    }

    OnDestroy {
      stopMotion()
      smsReceiver?.let { runCatching { context.unregisterReceiver(it) } }
      smsReceiver = null
    }
  }

  private fun ensureSmsReceiver() {
    if (smsReceiver != null) return
    val receiver = object : BroadcastReceiver() {
      override fun onReceive(c: Context?, intent: Intent?) {
        val phone = intent?.getStringExtra("phone") ?: return
        when (intent.action) {
          ACTION_SMS_SENT -> {
            val status = if (resultCode == Activity.RESULT_OK) "sent" else "failed"
            sendEvent("onSmsStatus", mapOf("phone" to phone, "status" to status))
          }
          ACTION_SMS_DELIVERED -> {
            val status = if (resultCode == Activity.RESULT_OK) "delivered" else "failed"
            sendEvent("onSmsStatus", mapOf("phone" to phone, "status" to status))
          }
        }
      }
    }
    val filter = IntentFilter().apply {
      addAction(ACTION_SMS_SENT)
      addAction(ACTION_SMS_DELIVERED)
    }
    if (Build.VERSION.SDK_INT >= 33) {
      context.registerReceiver(receiver, filter, Context.RECEIVER_NOT_EXPORTED)
    } else {
      context.registerReceiver(receiver, filter)
    }
    smsReceiver = receiver
  }

  private fun require(permission: String) {
    if (ContextCompat.checkSelfPermission(context, permission) != PackageManager.PERMISSION_GRANTED) {
      throw CodedException("ERR_PERMISSION", "$permission not granted", null)
    }
  }

  private fun notificationManager() =
    context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

  private fun ensureChannels() {
    val nm = notificationManager()
    if (nm.getNotificationChannel(CHANNEL_ALERTS) == null) {
      nm.createNotificationChannel(
        NotificationChannel(CHANNEL_ALERTS, "Driver alerts", NotificationManager.IMPORTANCE_HIGH).apply {
          enableVibration(true)
          vibrationPattern = longArrayOf(0, 250, 120, 250)
          setSound(
            RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION),
            AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_NOTIFICATION).build()
          )
        }
      )
    }
    if (nm.getNotificationChannel(CHANNEL_SOS) == null) {
      nm.createNotificationChannel(
        NotificationChannel(CHANNEL_SOS, "Crash and SOS", NotificationManager.IMPORTANCE_HIGH).apply {
          enableVibration(true)
          vibrationPattern = longArrayOf(0, 800, 400, 800, 400, 800)
          setBypassDnd(true)
          setSound(
            RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM),
            AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_ALARM).build()
          )
        }
      )
    }
  }

  /** Accelerometer (m/s², gravity included) at `hz`, latest gyro (rad/s) attached to each sample. */
  private fun startMotion(hz: Int) {
    stopMotion()
    val sm = context.getSystemService(Context.SENSOR_SERVICE) as SensorManager
    val accel = sm.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)
      ?: throw CodedException("ERR_NO_SENSOR", "No accelerometer", null)
    val gyro = sm.getDefaultSensor(Sensor.TYPE_GYROSCOPE)
    val thread = HandlerThread("sahi-motion").also { it.start() }
    val handler = Handler(thread.looper)
    val batch = ArrayList<Double>(7 * 32)
    val g = DoubleArray(3)
    // Event timestamps are elapsedRealtimeNanos; convert to wall-clock ms for JS.
    val offsetMs = System.currentTimeMillis() - SystemClock.elapsedRealtime()
    val listener = object : SensorEventListener {
      override fun onSensorChanged(e: SensorEvent) {
        if (e.sensor.type == Sensor.TYPE_GYROSCOPE) {
          g[0] = e.values[0].toDouble(); g[1] = e.values[1].toDouble(); g[2] = e.values[2].toDouble()
          return
        }
        batch.add(e.timestamp / 1e6 + offsetMs)
        batch.add(e.values[0].toDouble()); batch.add(e.values[1].toDouble()); batch.add(e.values[2].toDouble())
        batch.add(g[0]); batch.add(g[1]); batch.add(g[2])
      }

      override fun onAccuracyChanged(s: Sensor?, a: Int) {}
    }
    val periodUs = 1_000_000 / hz.coerceIn(10, 200)
    sm.registerListener(listener, accel, periodUs, handler)
    gyro?.let { sm.registerListener(listener, it, periodUs, handler) }
    // Flush to JS 5 times a second: one bridge call per 200 ms instead of one per sample.
    val flush = object : Runnable {
      override fun run() {
        if (batch.isNotEmpty()) {
          sendEvent("onMotion", mapOf("samples" to ArrayList(batch)))
          batch.clear()
        }
        handler.postDelayed(this, 200)
      }
    }
    handler.postDelayed(flush, 200)
    sensorThread = thread
    motionListener = listener
  }

  private fun stopMotion() {
    motionListener?.let {
      (context.getSystemService(Context.SENSOR_SERVICE) as SensorManager).unregisterListener(it)
    }
    motionListener = null
    sensorThread?.quitSafely()
    sensorThread = null
  }

  private fun joinWifi(ssid: String, password: String, promise: Promise) {
    val cm = context.getSystemService(ConnectivityManager::class.java)
    wifiCallback?.let { runCatching { cm.unregisterNetworkCallback(it) } }
    val builder = NetworkRequest.Builder()
      .addTransportType(NetworkCapabilities.TRANSPORT_WIFI)
      .removeCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
    if (ssid.isNotEmpty() && Build.VERSION.SDK_INT >= 29) {
      val spec = WifiNetworkSpecifier.Builder().setSsid(ssid)
      if (password.isNotEmpty()) spec.setWpa2Passphrase(password)
      builder.setNetworkSpecifier(spec.build())
    }
    var settled = false
    val cb = object : ConnectivityManager.NetworkCallback() {
      override fun onAvailable(network: Network) {
        cm.bindProcessToNetwork(network)
        if (!settled) { settled = true; promise.resolve(true) }
      }

      override fun onUnavailable() {
        if (!settled) { settled = true; promise.resolve(false) }
      }

      override fun onLost(network: Network) {
        cm.bindProcessToNetwork(null)
      }
    }
    wifiCallback = cb
    cm.requestNetwork(builder.build(), cb, 30_000)
  }

  companion object {
    // v2: notification sound attached (Android never mutates an existing channel id).
    const val CHANNEL_ALERTS = "alerts_v2"
    const val CHANNEL_SOS = "sos"
    const val ACTION_SMS_SENT = "edu.aast.rtdms.sahi.SMS_SENT"
    const val ACTION_SMS_DELIVERED = "edu.aast.rtdms.sahi.SMS_DELIVERED"
  }
}
