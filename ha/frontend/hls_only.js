// Live camera views on the Lenovo Smart Display use HLS instead of WebRTC.
// WebRTC arrives over UDP, and about one packet in five is lost on this display's Wi-Fi link.
// Home Assistant's WebRTC server does not resend them, so the picture runs for 20-30 seconds
// and then freezes until the next keyframe, over and over. HLS comes over the same TCP
// connection as the rest of the dashboard and plays at the camera's full frame rate.
// Home Assistant asks each camera which stream types it offers ("camera/capabilities");
// on the display only, the answer is trimmed to HLS. Every other browser is untouched.
(() => {
  if (!/mt8167s/i.test(navigator.userAgent) || window.__hlsOnly) return;
  window.__hlsOnly = true;
  const patch = (conn) => {
    const send = conn.sendMessagePromise.bind(conn);
    conn.sendMessagePromise = async (msg) => {
      const result = await send(msg);
      if (msg && msg.type === "camera/capabilities" && result && Array.isArray(result.frontend_stream_types)
          && result.frontend_stream_types.includes("hls")) {
        return { ...result, frontend_stream_types: ["hls"] };
      }
      return result;
    };
  };
  const wait = () => (window.hassConnection ? window.hassConnection.then(({ conn }) => patch(conn)) : setTimeout(wait, 200));
  wait();
})();
