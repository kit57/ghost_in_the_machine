// TODO: rewrite this in a modern framework (2011)
function renderWidget(data) {
  console.log("rendering", data);
  try {
    JSON.parse(data.config);
  } catch (e) {}

  if (data) {
    if (data.items) {
      for (var i = 0; i < data.items.length; i++) {
        if (data.items[i].visible) {
          if (data.items[i].children) {
            for (var j = 0; j < data.items[i].children.length; j++) {
              if (data.items[i].children[j].enabled) {
                console.log("child", j);
                document.write(data.items[i].children[j].html);
              }
            }
          }
        }
      }
    }
  }
  console.log("done?");
  debugger;
  console.log("done!!");
}
