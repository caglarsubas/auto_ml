declare module 'plotly.js-basic-dist' {
  namespace Plotly {
    function newPlot(
      divId: string,
      data: any[],
      layout?: Partial<Plotly.Layout>,
      config?: Partial<Plotly.Config>
    ): Promise<Plotly.PlotlyHTMLElement>;

    namespace Plots {
      function resize(divId: string): void;
    }
  }
  export = Plotly;
}