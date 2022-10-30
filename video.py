import os, sys
sys.path.append("./")
import gi
import datetime
import psutil
import math
import threading
import importlib
from utils.gst import create_gst_element
gi.require_version('Gst', '1.0')
from gi.repository import GLib, Gst
from services.logger import Log as logger
from app.video.source import Source
from app.video.gst_bus_handler import GstBusHandler
from app.video.streaming_handler import StreamingHandler
from app.video.recording_handler import RecordingHandler
from app.video.snapshots_handler import SnapshotsHandler
from app.video.FPS import PERF_DATA
import pyds

Gst.init(None)
perf_data = None

def pgie_src_pad_buffer_probe(pad,info,u_data):
    frame_number=0
    num_rects=0
    got_fps = False
    gst_buffer = info.get_buffer()
    if not gst_buffer:
        print("Unable to get GstBuffer ")
        return
    batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(gst_buffer))
    l_frame = batch_meta.frame_meta_list
    while l_frame is not None:
        try:
            frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
        except StopIteration:
            break

        
        stream_index = "stream{0}".format(frame_meta.pad_index)
        global perf_data
        perf_data.update_fps(stream_index)

        try:
            l_frame=l_frame.next
        except StopIteration:
            break

    return Gst.PadProbeReturn.OK

def main(args):

    global perf_data
    perf_data = PERF_DATA(3)

    # Create GST Pipeline
    pipeline = Gst.Pipeline()

    batched_push_timeout = int((1 / 120) * 1000 * 1000)
    max_latency =  int((1 / 10) * 1000 * 1000)

    # Muxer
    streammux = create_gst_element("nvstreammux", "muxer")
    # streammux.set_property('live-source', True)
    streammux.set_property('sync-inputs', False)
    # streammux.set_property('width', 1280)
    # streammux.set_property('height', 720)
    streammux.set_property('batch-size', 3) # Maximum number of frames in a batch.
    # streammux.set_property('batched-push-timeout', batched_push_timeout) # Timeout in microseconds to wait after the first buffer is available to push the batch even if a complete batch is not formed.
    pipeline.add(streammux)

    # Source #1
    source_1 = create_gst_element("nvv4l2camerasrc", "source-1")
    source_1.set_property('device', '/dev/video0')
    source_1.set_property('do-timestamp', True)
    source_1.set_property('bufapi-version', True)
    pipeline.add(source_1)

    caps_src_1 = create_gst_element("capsfilter", "source-1-caps")
    caps_src_1.set_property('caps', Gst.Caps.from_string(f"video/x-raw(memory:NVMM), width=(int)1280, height=(int)720, framerate=(fraction)30/1"))
    pipeline.add(caps_src_1)
    source_1.link(caps_src_1)

    convertor_src_1 = create_gst_element("nvvideoconvert", "source-1-convertor")
    pipeline.add(convertor_src_1)
    caps_src_1.link(convertor_src_1)

    padname = f"sink_0"
    sinkpad = streammux.get_request_pad(padname)
    if not sinkpad:
        logger.error("[Media Server] - Unable to create source sink pad")
        return

    srcpad = convertor_src_1.get_static_pad("src")
    if not srcpad:
        logger.error("[Media Server] - Unable to create source src pad")
        return
    
    logger.info("[Media Server] - Linking source with streammux")
    srcpad.link(sinkpad)

    # Source #2
    source_2 = create_gst_element("nvv4l2camerasrc", "source-2")
    source_2.set_property('device', '/dev/video1')
    source_2.set_property('do-timestamp', True)
    source_2.set_property('bufapi-version', True)
    pipeline.add(source_2)

    caps_src_2 = create_gst_element("capsfilter", "source-2-caps")
    caps_src_2.set_property('caps', Gst.Caps.from_string(f"video/x-raw(memory:NVMM), width=(int)1280, height=(int)720, framerate=(fraction)30/1"))
    pipeline.add(caps_src_2)
    source_2.link(caps_src_2)

    convertor_src_2 = create_gst_element("nvvideoconvert", "source-2-convertor")
    pipeline.add(convertor_src_2)
    caps_src_2.link(convertor_src_2)

    padname = f"sink_1"
    sinkpad = streammux.get_request_pad(padname)
    if not sinkpad:
        logger.error("[Media Server] - Unable to create source sink pad")
        return

    srcpad = convertor_src_2.get_static_pad("src")
    if not srcpad:
        logger.error("[Media Server] - Unable to create source src pad")
        return
    
    logger.info("[Media Server] - Linking source with streammux")
    srcpad.link(sinkpad)


    # Source #3
    source_3 = create_gst_element("nvv4l2camerasrc", "source-3")
    source_3.set_property('device', '/dev/video2')
    source_3.set_property('do-timestamp', True)
    source_3.set_property('bufapi-version', True)
    pipeline.add(source_3)

    caps_src_3 = create_gst_element("capsfilter", "source-3-caps")
    caps_src_3.set_property('caps', Gst.Caps.from_string(f"video/x-raw(memory:NVMM), width=(int)1280, height=(int)720, framerate=(fraction)30/1"))
    pipeline.add(caps_src_3)
    source_3.link(caps_src_3)

    convertor_src_3 = create_gst_element("nvvideoconvert", "source-3-convertor")
    pipeline.add(convertor_src_3)
    caps_src_3.link(convertor_src_3)

    padname = f"sink_2"
    sinkpad = streammux.get_request_pad(padname)
    if not sinkpad:
        logger.error("[Media Server] - Unable to create source sink pad")
        return

    srcpad = convertor_src_3.get_static_pad("src")
    if not srcpad:
        logger.error("[Media Server] - Unable to create source src pad")
        return
    
    logger.info("[Media Server] - Linking source with streammux")
    srcpad.link(sinkpad)


    # Queue 1
    queue_1 = create_gst_element("queue", "first-queue")
    pipeline.add(queue_1)
    streammux.link(queue_1)

    # Detection
    ai_model = create_gst_element("nvinfer", "first-detector")
    ai_model.set_property("config-file-path", "/edge-appliance/resources/models/XfWWqUAnlwFbVxZFEtgkSss8XT86l5v8FScBjVviYY2SA8rQ1rJvcZMSFEGk/config.txt")
    # ai_model.set_property('config-file-path', "/opt/nvidia/deepstream/deepstream/samples/configs/deepstream-app/config_infer_primary.txt")
    # ai_model.set_property("batch-size", 1)
    pipeline.add(ai_model)
    queue_1.link(ai_model)

    # Queue 2
    queue_2 = create_gst_element("queue2", "second-queue")
    pipeline.add(queue_2)
    ai_model.link(queue_2)

    # Tracker
    logger.info(f"[Media Server] - Tracker 1280x720")
    tracker = create_gst_element("nvtracker", "tracker")
    tracker.set_property('tracker-width', 640)
    tracker.set_property('tracker-height', 384)
    tracker.set_property('ll-lib-file', "/opt/nvidia/deepstream/deepstream/lib/libnvds_nvmultiobjecttracker.so")
    tracker.set_property('ll-config-file', "/edge-appliance/resources/config/nvds-tracker.yml")
    # tracker.set_property('gpu-id', 0)
    # tracker.set_property('display-tracking-id', True)
    # tracker.set_property('compute-hw', 2) 
    # tracker.set_property('enable-past-frame', 1)
    # tracker.set_property('enable-batch-process', 1)
    pipeline.add(tracker)
    queue_2.link(tracker)

    # Queue 3
    queue_3 = create_gst_element("queue", "third-queue")
    pipeline.add(queue_3)
    tracker.link(queue_3)

    # Analytics Converter
    # analytics_convertor_caps = create_gst_element("capsfilter", "analytics-convertor-caps")
    # analytics_convertor_caps.set_property("caps", Gst.Caps.from_string("video/x-raw(memory:NVMM), format=RGBA"))
    # pipeline.add(analytics_convertor_caps)
    # tracker.link(analytics_convertor_caps)

    # Analitics 
    analytics = create_gst_element("nvdsanalytics", "analytics")
    analytics.set_property("config-file", "/edge-appliance/resources/config/nvds-analytics.txt")
    pipeline.add(analytics)
    queue_3.link(analytics)

    # Queue 4
    queue_4 = create_gst_element("queue", "fourth-queue")
    pipeline.add(queue_4)
    analytics.link(queue_4)

    # Tiler
    tiler = create_gst_element("nvmultistreamtiler", "nvtiler")
    tiler.set_property("rows", 2)
    tiler.set_property("columns", 2)
    tiler.set_property('width', 1280)
    tiler.set_property('height', 720)
    pipeline.add(tiler)
    queue_4.link(tiler)

    # Queue 5
    queue_5 = create_gst_element("queue", "fifth-queue")
    pipeline.add(queue_5)
    tiler.link(queue_5)

    # OSD Converter
    display_convertor = create_gst_element("nvvideoconvert", "display-converter")
    pipeline.add(display_convertor)
    queue_5.link(display_convertor)

    # Queue 6
    queue_6 = create_gst_element("queue", "sixth-queue")
    pipeline.add(queue_6)
    display_convertor.link(queue_6)

    # Nvosd
    display_nvosd = create_gst_element("nvdsosd", "display-nvosd")
    pipeline.add(display_nvosd)
    display_nvosd.set_property('process-mode', 2)
    display_nvosd.set_property('display-text', True)
    display_nvosd.set_property('display-mask', True)
    display_nvosd.set_property('display-bbox', True)
    display_nvosd.set_property('display-clock', True)
    display_nvosd.set_property('clock-font', 'Hack')
    display_nvosd.set_property('clock-font-size', 16)
    display_nvosd.set_property('x-clock-offset', 10)
    display_nvosd.set_property('y-clock-offset', 5)
    display_nvosd.set_property('clock-color', 0xff0000ff)
    queue_6.link(display_nvosd)


    # Queue 7
    queue_7 = create_gst_element("queue", "seventh-queue")
    pipeline.add(queue_7)
    display_nvosd.link(queue_7)

    # If the app is running on production we don't show the display
    # display_sink = create_gst_element("fpsdisplaysink", "display-tiler-sink")
    # display_sink.set_property("sync", False)
    # display_sink.set_property("video-sink", "fakesink")
    # display_sink.set_property("text-overlay", False)
    # pipeline.add(display_sink)
    # queue_7.link(display_sink)

    # Transform
    display_transform = create_gst_element("nvegltransform", "display-transform")
    pipeline.add(display_transform)
    queue_7.link(display_transform)
    
    # Queue 9
    queue_9 = create_gst_element("queue", "nineth-queue")
    pipeline.add(queue_9)
    display_transform.link(queue_9)

    # Sink
    display_sink = create_gst_element("nveglglessink", "display-tiler-sink")
    display_sink.set_property("qos", True)
    display_sink.set_property("sync", False)
    pipeline.add(display_sink)
    queue_9.link(display_sink)
        

    # Link Probe to analitycs
    logger.info("[Media Server] - Linking metadata probe")
    sink_pad = tiler.get_static_pad("sink")
    if not sink_pad:
        logger.error("[Media Server] - Unable to get probe sink pad")
        return
    else:
        sink_pad.add_probe(Gst.PadProbeType.BUFFER, pgie_src_pad_buffer_probe, 0)

    # if is_recording:
    logger.info("[FPS] - Start timer")
    perf_data.perf_print_callback()

    # List the sources
    logger.info("[Media Server] - Play Gst Pipeline")
    pipeline.set_state(Gst.State.PLAYING)

    logger.info('[Media Server] - Stopped Media Server Service')
    loop = GLib.MainLoop()

    # start play back and listed to events		
    pipeline.set_state(Gst.State.PLAYING)
    try:
        loop.run()
    except:
        pass
    # cleanup
    logger.info("Exiting app")

    pipeline.set_state(Gst.State.NULL)

    
if __name__ == '__main__':
    sys.exit(main(sys.argv))