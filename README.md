### Network Video Recorder System for Orangepi5

- Dropped Jetson Nano hardware due issues on my board. Now using Orangepi5 with Armbian image (cli-server).  
(hardware decoding by using rockchip mpp ffmpeg port by selecting 'software' decoders 'h264' and 'hevc'. [More here](https://github.com/Motion-Project/motion/discussions/1710#discussioncomment-10467237)

- Uses [Motion Project](https://github.com/Motion-Project/motion)

 - Due Yoosee Ip Cameras (what I have) [abuse of RTSP protocol](https://stackoverflow.com/q/66280861/1207193) I had to create a patch for ffmpeg/libavformat (`RTSP_lower_transport_TCP.patch` modifies rtsp.c and rtsp.h) and make connection using rtsp/tcp possible. Hence ffmpeg must be compiled from source. 


### Motion Configuration Notes 

#### About *.conf files parameters
________________________

#### `width`x`height`

- If motion complains the network camera is sending pictures in a different size. And that it's resizing the images.
It is indeed resizing the image using swscale.lib from ffmpeg. Your width, heigh passed is wrong or not being parsed due some tipo.
I was using `width=640` when correct is without `=`. Each camera must provide its width, height for low resolution outsite `camera_params`.
For high resolution stream you can provide width, height on camera params.

More details: motion uses `ffmpeg` (`libswscale/swscale.c`) `sws_getContext`  and `sws_scale` on `src/netcam_rtsp.c` for software resizing rtsp frames to provided `width`x`height`.

________________________

#### `capture_rate` and `frame_rate` from docs

To avoid the decoding and disconnection errors, it is recommended that the FPS (`frame_rate`) of the camera be adjusted where possible (not possible for me).
Generally, it is preferable to have the FPS (`frame_rate`) of the camera be *slightly lower than the `capture_rate`* of Motion. This allows for the decoder to perform better and reduce decoding errors. 

________________________
#### Comments '#'

Don't comment on the same line of a parameter. It's not allowed!
