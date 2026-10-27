using Microsoft.AnalysisServices.Tabular;
using System.Text.Json;

if (args.Length != 1)
{
    Console.Error.WriteLine("Usage: PowerBiModelCheck <SemanticModel/definition directory>");
    return 2;
}

try
{
    // Parse with Microsoft's own TOM/TMDL serializer. No server, credentials,
    // Desktop process, refresh or DAX engine is invoked.
    var model = TmdlSerializer.DeserializeModelFromFolder(Path.GetFullPath(args[0]));
    if (model.Tables.Count == 0)
        throw new InvalidOperationException("Semantic model contains no tables.");
    Console.WriteLine(System.Text.Json.JsonSerializer.Serialize(new
    {
        tmdlParsed = true,
        tables = model.Tables.Select(t => new { name = t.Name, columns = t.Columns.Count, measures = t.Measures.Count }).ToArray(),
        daxEngineExecuted = false,
        desktopRenderVerified = false
    }, new JsonSerializerOptions { WriteIndented = true }));
    return 0;
}
catch (Exception error)
{
    Console.Error.WriteLine(error.Message);
    return 1;
}
