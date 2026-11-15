function lf_octave(script)
  % Runs a MATLAB script under GNU Octave the way a lab report needs it:
  % no windows, the image package loaded, and every figure saved as figure_NN.png
  % in the working folder so it can go into the report.
  more off;
  warning('off', 'all');
  pkgs = {'image', 'signal', 'statistics', 'control', 'communications'};
  for k = 1:numel(pkgs)
    try
      pkg('load', pkgs{k});
    catch
    end
  end
  try
    graphics_toolkit('gnuplot');   % the one toolkit that draws without a display
  catch
  end
  set(0, 'defaultfigurevisible', 'off');
  status = 0;
  try
    evalin('base', sprintf('run(''%s'');', script));
  catch err
    fprintf('error: %s\n', err.message);
    for k = 1:numel(err.stack)
      if isempty(strfind(err.stack(k).name, 'lf_octave'))
        fprintf('  in %s, line %d\n', err.stack(k).name, err.stack(k).line);
      end
    end
    status = 1;
  end
  figs = sort(findall(0, 'type', 'figure'));
  for k = 1:min(numel(figs), 12)
    try
      print(figs(k), sprintf('figure_%02d.png', k), '-dpng', '-r110');
    catch
    end
  end
  exit(status);
end
