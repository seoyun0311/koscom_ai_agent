export const UIActions = {
    apply(actions) {
      if (!Array.isArray(actions)) actions = [actions];
  
      actions.forEach(action => {
        switch(action.action) {
          case "highlight":
            Dashboard.highlight(action.target, action.color);
            break;
  
          case "update_value":
            Dashboard.updateValue(action.target, action.value);
            break;
  
          case "show_widget":
            Dashboard.addWidget(action.widget);
            break;
  
          case "remove_widget":
            Dashboard.removeWidget(action.target);
            break;
        }
      });
    }
  }
  